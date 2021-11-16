import logging
import sys
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from magic_filter import F

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from models import Message, ExceptUser, engine

import settings as bs

bot = Bot(bs.TOKEN, parse_mode="HTML")
dp = Dispatcher()

logger = logging.getLogger('bot')



def save_message(message, text, msg_type, session, media=None):
	msg = Message(
		msgid=message.message_id,
		sender=message.from_user.id,
		sender_name=message.from_user.first_name,
		type=msg_type,
		text=text,
		media=media,
		sent=datetime.utcnow()
	)
	session.add(msg)



async def check_duplicates(message, text, msg_type, session, media=None):
	'''
	message - aiogram Message
	text - text of the message. For media messages without caption could be none
	msg_type - str - 'text'/'photo'/'video'
	session - sqlalchemy ORM session
	media - file ids for media messages. For text messages expected to be None

	Returns:
	duplicate = first database entry
	'''

	# Pardoned users handling
	is_exception = session.execute(
		select(ExceptUser.id).
		filter_by(uid=message.from_user.id)
	).first()

	chat_admins = [x.user.id for x in await bot.get_chat_administrators(chat_id=message.chat.id)]
	sender_is_admin = message.from_user.id in chat_admins

	if is_exception or sender_is_admin:
		return

	# Query
	time_start = datetime.utcnow() - timedelta(minutes=bs.RESET_PERIOD)
	duplicate = session.execute(
		select(Message).
		filter_by(
			type=msg_type,
			sender=message.from_user.id,
			text=text,
			media=media,
		).filter(
			Message.sent > time_start
		)
	).first()
	duplicate = duplicate.Message if duplicate is not None else None

	# Result processing
	logger.info(f'Message: {text}|{media} ({msg_type}); Sender: {message.from_user.id}; Database entry: {duplicate}')

	if duplicate is None:
		save_message(message, text, msg_type, session, media=media)

	elif not duplicate.replied:
		# Assume that this is the second repeat duplicate, while reply is sent on first one
		session.execute(
			update(Message).
			where(
				Message.sender == message.from_user.id,
				Message.type == msg_type,
				Message.text == text,
				Message.media == media,
				Message.sent > time_start
			).
			values(replied=True)
		)
		# After this query is commited duplicate object is not accessed within session to prevent refetching of replied attribute
		# Thus preserving it in expired/detached state

	return duplicate



async def process_duplicate(message, duplicate):
	if not duplicate.replied or bs.ALLOW_REPEATING_WARNINGS:
		sender = message.from_user
		text = f'<a href="tg://user?id={sender.id}">@{sender.first_name}</a>, your message has been deleted. Reason: duplicate message (id {duplicate.msgid})'
		await message.answer(text)
	await message.delete()



@dp.message(commands=['except'])
async def except_handler(message: types.Message):
	if message.from_user.id not in bs.ADMIN_IDS:
		return

	args = message.text.split(' ')

	if len(args) < 1:
		await message.answer('Usage: /except <user id>. Use @getidsbot to get user id from a message.')
		return

	target = args[-1]
	with Session(engine) as session:
		user = ExceptUser(uid=target)
		session.add(user)
		session.commit()

	await message.answer(f'Added {target} to exceptions')



@dp.message(commands=['delete'])
async def delete_handler(message: types.Message):
	if message.from_user.id not in bs.ADMIN_IDS:
		return

	args = message.text.split(' ')

	if len(args) < 1:
		await message.answer('Usage: /delete <message id>.')
		return

	msgid = args[-1]
	with Session(engine) as session:
		session.execute(
			delete(Message).
			where(Message.msgid == msgid)
		)
		session.commit()

	try:
		await bot.delete_message(chat_id=message.chat.id, message_id=msgid)
	except Exception as e:
		logging.info(f'Error deleting message {msgid}: {e}')

	await message.answer(f'Message {msgid} has been deleted')



@dp.message(F.chat.type.in_(['group', 'supergroup']), content_types=['text'])
async def text_handler(message: types.Message):
	entities = message.entities or []
	has_command = any(x.type == 'bot_command' for x in entities)
	if has_command and bs.ALLOW_DUPLICATE_COMMANDS:
		return

	text = message.text

	with Session(engine, expire_on_commit=False) as session:
		duplicate = await check_duplicates(message, text=text, msg_type='text', session=session)
		session.commit()

	if duplicate is not None:
		await process_duplicate(message, duplicate)



@dp.message(F.chat.type.in_(['group', 'supergroup']), content_types=['photo'])
async def photo_handler(message: types.Message):
	photos = message.photo
	file_id = photos[0].file_unique_id
	caption = message.caption

	with Session(engine, expire_on_commit=False) as session:
		photo_duplicate = await check_duplicates(message, text=caption, msg_type='photo', session=session, media=file_id)

		if caption:
			# Additionally, save caption as text message
			await check_duplicates(message, text=caption, msg_type='text', session=session)

		session.commit()

	if photo_duplicate is not None:
		await process_duplicate(message, photo_duplicate)



@dp.message(F.chat.type.in_(['group', 'supergroup']), content_types=['video'])
async def video_handler(message: types.Message):
	file_id = message.video.file_size
	caption = message.caption

	with Session(engine, expire_on_commit=False) as session:
		video_duplicate = await check_duplicates(message, text=caption, msg_type='video', session=session, media=file_id)

		if caption:
			# Additionally, save caption as text message
			await check_duplicates(message, text=caption, msg_type='text', session=session)

		session.commit()

	if video_duplicate is not None:
		await process_duplicate(message, video_duplicate)



@dp.message(F.chat.type.in_(['group', 'supergroup']), content_types=['animation'])
async def animation_handler(message: types.Message):
	file_id = message.animation.file_size
	caption = message.caption

	with Session(engine, expire_on_commit=False) as session:
		animation_duplicate = await check_duplicates(message, text=caption, msg_type='animation', session=session, media=file_id)

		if caption:
			# Additionally, save caption as text message
			await check_duplicates(message, text=caption, msg_type='text', session=session)

		session.commit()

	if animation_duplicate:
		await process_duplicate(message, animation_duplicate)



@dp.message(F.chat.type.not_in_(['group', 'supergroup']))
async def fallback_handler(message: types.Message):
	await message.answer('Sorry, I only work in group chats! Add me to a group and give me administrator permissions to use my features')



def main():
	# Configure logger
	if bs.LOG_FILE:
		handler = logging.FileHandler(bs.LOG_FILE, mode='a')
	else:
		handler = logging.StreamHandler(sys.stdout)

	log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(log_format)

	logger.addHandler(handler)
	logger.setLevel(logging.DEBUG)

	# Configure bot
	logger.info('Starting the bot')
# 	dp.run_polling(bot)
	start_webhook(
		dispatcher=dp,
		webhook_path=f"/webhook/2120771713:AAHBiz3ygcXlB_MkBdg6Bc0YQt_YBQka2aA",
		skip_updates=True,
		host="0.0.0.0",
		port=int(os.getenv("PORT"))
	)


if __name__ == "__main__":
	main()
