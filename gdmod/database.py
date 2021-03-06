import sqlite3
import datetime
import logging

class Database:

    def __init__(self, databaseFile=None):
        self.databaseFile = databaseFile if databaseFile else 'gd.db'
        self.initialize_database()

    def create_connection(self):
        return sqlite3.connect(self.databaseFile, detect_types=sqlite3.PARSE_DECLTYPES)

    def initialize_database(self):
        with self.create_connection() as conn:
            c = conn.cursor()

            # Audit table of all the processed text messages
            c.execute("CREATE TABLE IF NOT EXISTS text_messages (" +
                       "sid text UNIQUE, " + 
                       "created_at timestamp, " + 
                       "sent_at timestamp, " + 
                       "phone_from text, " + 
                       "phone_to text, " + 
                       "direction text, " + 
                       "status text, " + 
                       "status_message text, " + 
                       "error_code text, " + 
                       "error_message text, " + 
                       "body text)")

            # Table that will lock opening/closing the garage door from text messages
            c.execute("CREATE TABLE IF NOT EXISTS door_lock (id integer UNIQUE, locked_at timestamp)")

            # Keep track of all the times the garage door was opened/closed
            c.execute("CREATE TABLE IF NOT EXISTS door_state_history (state text, changed_at timestamp)")

            # Keep track of all of the challenges for a phone number in case challenges are used
            c.execute("CREATE TABLE IF NOT EXISTS door_challenge (code text, text_message_sid text, challenged_at timestamp)")

    def destroy_database(self):
        with self.create_connection() as conn:
            c = conn.cursor()
            c.execute("DROP TABLE IF EXISTS text_messages")
            c.execute("DROP TABLE IF EXISTS door_lock")
            c.execute("DROP TABLE IF EXISTS door_state_history")
            c.execute("DROP TABLE IF EXISTS door_challenge")


    # ------------------------------------------------------------------------------------------------------------
    # text_messages
    # ------------------------------------------------------------------------------------------------------------

    def insert_text_message(self, textMessage):
        if 'sid' not in textMessage:
            raise ValueError('Unable to insert, no text message SID found in message: {}'.format(textMessage))

        logging.debug('inserting text message: {}'.format(textMessage))

        with self.create_connection() as conn:
            c = conn.cursor()
            insert = ("INSERT INTO text_messages (sid, created_at, sent_at, phone_from, phone_to, direction, status, status_message, error_code, error_message, body) " +
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
            c.execute(insert, (
                textMessage.get("sid"), 
                textMessage.get("createdAt", datetime.datetime.now()), 
                textMessage.get("sentAt", datetime.datetime.now()), 
                textMessage.get("phoneFrom", None), 
                textMessage.get("phoneTo", None), 
                textMessage.get("direction", None), 
                textMessage.get("status", None), 
                textMessage.get("statusMessage", None), 
                textMessage.get("errorCode", None), 
                textMessage.get("errorMessage", None), 
                textMessage.get("body", None)))

        #with self.create_connection() as conn:
        #    c = conn.cursor()
        #    for row in c.execute("select * from text_messages"):
        #        logging.debug('[text_messages] : {}'.format(row))

    def update_text_message_status(self, sid, status, statusMessage=None):
        if sid is None or status is None:
            raise ValueError("Unable to update message to '{}'' because some values were missing for sid: '{}'".format(status, sid))

        with self.create_connection() as conn:
            c = conn.cursor()
            update = ("UPDATE text_messages SET status = ?, status_message = ? WHERE sid = ?")
            c.execute(update, (status, statusMessage, sid,))
            for row in c.execute("select * from text_messages WHERE sid = ?", (sid,)):
                logging.info('updated: {}'.format(row))

    def find_messages(self, dateFrom):
        logging.debug("Selecting from: {}".format(dateFrom))
        
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            textMessages = []
            c = conn.cursor()
            select = "SELECT * FROM text_messages WHERE created_at >= ?"
            for row in c.execute(select, (dateFrom,)):
                message = self.__translate_row_to_message(row)
                if message is not None:
                    textMessages.append(message)
            return textMessages

    def __translate_row_to_message(self, row):
        if row is not None:
            return {
                "sid": row["sid"], 
                "createdAt": row["created_at"],
                "sentAt": row["sent_at"],
                "phoneFrom": row["phone_from"],
                "phoneTo": row["phone_to"],
                "direction": row["direction"],
                "status": row["status"],
                "statusMessage": row["status_message"],
                "errorCode": row["error_code"],
                "errorMessage": row["error_message"],
                "body": row["body"]
            }
        return None

    # ------------------------------------------------------------------------------------------------------------
    # door_lock
    # ------------------------------------------------------------------------------------------------------------

    def insert_door_lock(self, lockedAt=None):
        lockedAt = lockedAt if lockedAt else datetime.datetime.now()

        with self.create_connection() as conn:
            try:
                c = conn.cursor()
                insert = ("INSERT INTO door_lock (id, locked_at) VALUES (1, ?)")
                c.execute(insert, (lockedAt,))
            except sqlite3.IntegrityError:
                raise ValueError('Door lock already exists')

    def remove_door_lock(self):
        with self.create_connection() as conn:
            c = conn.cursor()
            delete = ("DELETE FROM door_lock")
            c.execute(delete)

    def find_door_lock(self):
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            select = ("SELECT * FROM door_lock")
            c.execute(select)
            row = c.fetchone()
            if row is not None:
                return row["locked_at"]
            return None

    # ------------------------------------------------------------------------------------------------------------
    # door_state_history
    # ------------------------------------------------------------------------------------------------------------

    def insert_door_state_history(self, doorState, changedAt=None):
        changedAt = changedAt if changedAt else datetime.datetime.now()

        with self.create_connection() as conn:
            c = conn.cursor()
            insert = ("INSERT INTO door_state_history (state, changed_at) VALUES (?, ?)")
            c.execute(insert, (doorState, changedAt, ))

    def find_door_state_histories(self, fromDateTime=None):
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            histories = []
            c = conn.cursor()
            select = ("SELECT * FROM door_state_history WHERE changed_at > ?")
            for row in c.execute(select, (fromDateTime,)):
                histories.append({"state": row["state"], "changedAt": row["changed_at"]})
            return histories

    def find_door_state_history_latest(self):
        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            select = ("SELECT * FROM door_state_history ORDER BY changed_at DESC LIMIT 1")
            c.execute(select)
            row = c.fetchone()
            if row is not None:
                return {"state": row["state"], "changedAt": row["changed_at"]}
            return None

    # ------------------------------------------------------------------------------------------------------------
    # door_challenge
    # ------------------------------------------------------------------------------------------------------------

    def insert_door_challenge(self, code, textMessageSid, challengedAt=None):
        challengedAt = challengedAt if challengedAt else datetime.datetime.now()
        if code is None: raise ValueError('Unable to insert challenge, no code provided')
        if textMessageSid is None: raise ValueError('Unable to insert challenge, no textMessageSid provided')

        logging.debug("insert_door_challenge - code: {}, textMessageSid:{}, challengedAt:{}".format(code, textMessageSid, challengedAt))
        with self.create_connection() as conn:
            c = conn.cursor()
            insert = ("INSERT INTO door_challenge (code, text_message_sid, challenged_at) VALUES (?, ?, ?)")
            c.execute(insert, (code, textMessageSid, challengedAt, ))

        #with self.create_connection() as conn:
        #    c = conn.cursor()
        #    for row in c.execute("select * from door_challenge"):
        #        logging.debug('[door_challenge] : {}'.format(row))


    def delete_door_challenge(self, code):
        if code is None: raise ValueError('Unable to delete challenge, no code provided')

        with self.create_connection() as conn:
            c = conn.cursor()
            delete = ("DELETE FROM door_challenge WHERE code = ?")
            c.execute(delete, (code, ))

    def find_door_challenge(self, code, challengedAt=None):
        if code is None: return None

        # Default challenges to be only valid for 15 minutes by default
        challengedAt = challengedAt if challengedAt else datetime.datetime.now() - datetime.timedelta(minutes=15)

        with self.create_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            select = ("SELECT tm.* FROM text_messages tm INNER JOIN door_challenge dc ON dc.text_message_sid = tm.sid WHERE dc.code = ? and dc.challenged_at > ?")
            c.execute(select, (code, challengedAt,))
            row = c.fetchone()
            if row is not None:
                return self.__translate_row_to_message(row)
            return None

