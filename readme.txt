SETTINGS:
ALLOW_REPEATING_WARNINGS - if set to False, bot will only reply once when encountering duplciate message more than once
ALLOW_DUPLICATE_COMMANDS - if set to True, bot will not delete duplicate messages if they contain a command (e.g. /menu)
RESET_PERIOD - time in minutes, after which messages are not considered duplicates
ADMIN_IDS - list of telegram ids of users who can use commands

COMMANDS:
/except <telegram id> - saves user telegram id into exception list. Bot doesn't remove duplicate messages from users in exception list.
/delete <message id> - removes message from bot memory and deletes it from chat
