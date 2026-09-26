import re
import time

from slack_sdk import WebClient


class Driver(object):
    """Functional tests driver. It handles the communication with slack api, so that
    the tests code can concentrate on higher level logic.
    """
    def __init__(self, driver_apitoken, driver_username, testbot_username, channel, private_channel):
        self.web_client = WebClient(token=driver_apitoken)
        self.driver_username = driver_username
        self.driver_userid = None
        self.test_channel = channel
        self.test_private_channel = private_channel
        self.users = {}
        self.testbot_username = testbot_username
        self.testbot_userid = None
        # public channel
        self.cm_chan = None
        # direct message channel
        self.dm_chan = None
        # private private_channel channel
        self.gm_chan = None
        self._start_ts = time.time()
        self._last_sent_ts = None

    def start(self):
        self._connect()
        self._start_dm_channel()
        self._join_test_channel()

    def wait_for_bot_online(self):
        self._wait_for_bot_presense(True)
        # sleep to allow bot connection to stabilize
        time.sleep(2)

    def wait_for_bot_offline(self):
        self._wait_for_bot_presense(False)

    def _wait_for_bot_presense(self, online):
        for _ in range(10):
            time.sleep(2)
            if online and self._is_testbot_online():
                break
            if not online and not self._is_testbot_online():
                break
        else:
            raise AssertionError('test bot is still {}'.format('offline' if online else 'online'))

    def _format_message(self, msg, tobot=True, toname=False, colon=True,
                        space=True):
        colon = ':' if colon else ''
        space = ' ' if space else ''
        if tobot:
            msg = u'<@{}>{}{}{}'.format(self.testbot_userid, colon, space, msg)
        elif toname:
            msg = u'{}{}{}{}'.format(self.testbot_username, colon, space, msg)
        return msg

    def send_direct_message(self, msg, tobot=False, colon=True):
        msg = self._format_message(msg, tobot, colon)
        self._send_message_to_bot(self.dm_chan, msg)

    def _send_channel_message(self, chan, msg, **kwargs):
        msg = self._format_message(msg, **kwargs)
        self._send_message_to_bot(chan, msg)

    def send_channel_message(self, msg, **kwargs):
        self._send_channel_message(self.cm_chan, msg, **kwargs)

    def send_private_channel_message(self, msg, **kwargs):
        self._send_channel_message(self.gm_chan, msg, **kwargs)

    def wait_for_bot_direct_message(self, match):
        self._wait_for_bot_message(self.dm_chan, match, tosender=False)

    def wait_for_bot_direct_messages(self, matches):
        for match in matches:
            self._wait_for_bot_message(self.dm_chan, match, tosender=False)

    def wait_for_bot_channel_message(self, match, tosender=True):
        self._wait_for_bot_message(self.cm_chan, match, tosender=tosender)

    def wait_for_bot_private_channel_message(self, match, tosender=True):
        self._wait_for_bot_message(self.gm_chan, match, tosender=tosender)

    def wait_for_bot_channel_thread_message(self, match, tosender=False):
        self._wait_for_bot_message(self.gm_chan, match, tosender=tosender, thread=True)

    def wait_for_bot_private_channel_thread_message(self, match, tosender=False):
        self._wait_for_bot_message(self.gm_chan, match, tosender=tosender,
                                   thread=True)

    def ensure_only_specificmessage_from_bot(self, match, wait=5, tosender=False):
        if tosender is True:
            match = r'^\<@{}\>: {}$'.format(self.driver_userid, match)
        else:
            match = u'^{}$'.format(match)

        for _ in range(wait):
            time.sleep(1)
            for msg in self._bot_messages_since_start(self.cm_chan):
                if re.match(match, msg['text'], re.DOTALL) is None:
                    raise AssertionError(
                        u'expected to get message matching "{}", but got message "{}"'.format(match, msg['text']))

    def ensure_no_channel_reply_from_bot(self, wait=5):
        for _ in range(wait):
            time.sleep(1)
            for msg in self._bot_messages_since_start(self.cm_chan):
                raise AssertionError(
                    'expected to get nothing, but got message "{}"'.format(msg['text']))

    def wait_for_file_uploaded(self, name, maxwait=30):
        for _ in range(maxwait):
            time.sleep(1)
            if self._has_uploaded_file(name):
                break
        else:
            raise AssertionError('expected to get file "{}", but got nothing'.format(name))

    def ensure_reaction_posted(self, emojiname, maxwait=5):
        for _ in range(maxwait):
            time.sleep(1)
            if self._has_reacted(emojiname):
                break
        else:
            raise AssertionError('expected to get reaction "{}", but got nothing'.format(emojiname))

    def _send_message_to_bot(self, channel, msg):
        self.clear_events()
        self._start_ts = time.time()
        response = self.web_client.chat_postMessage(
            channel=channel, text=msg, username=self.driver_username)
        self._last_sent_ts = response['ts']

    def _wait_for_bot_message(self, channel, match, maxwait=60, tosender=True, thread=False):
        for _ in range(maxwait):
            time.sleep(1)
            if self._has_got_message(channel, match, tosender=tosender, thread=thread):
                break
        else:
            raise AssertionError('expected to get message like "{}", but got nothing'.format(match))

    def _channel_messages(self, channel, thread=False, start=None, end=None):
        if thread:
            if not self._last_sent_ts:
                return []
            response = self.web_client.conversations_replies(
                channel=channel, ts=self._last_sent_ts)
            return response.get('messages', [])

        oldest = start or self._start_ts
        latest = end or time.time()
        response = self.web_client.conversations_history(
            channel=channel, oldest=oldest, latest=latest)
        return response.get('messages', [])

    def _has_got_message(self, channel, match, tosender=True, thread=False, start=None, end=None):
        if tosender is True:
            match = r'\<@{}\>: {}'.format(self.driver_userid, match)
        for msg in self._channel_messages(channel, thread=thread, start=start, end=end):
            if msg.get('type') == 'message' and 'text' in msg and \
                    re.match(match, msg['text'], re.DOTALL):
                return True
        return False

    def _bot_messages_since_start(self, channel):
        for msg in self._channel_messages(channel):
            if self._is_bot_message(msg):
                yield msg

    def _fetch_users(self):
        response = self.web_client.users_list()
        for user in response.get('members', []):
            self.users[user['name']] = user['id']

        self.testbot_userid = self.users[self.testbot_username]
        self.driver_userid = self.users[self.driver_username]

    def _connect(self):
        r = self.web_client.auth_test()
        self.driver_username = r['user']
        self.driver_userid = r['user_id']
        self._fetch_users()

    def _start_dm_channel(self):
        """Start a slack direct messages channel with the test bot"""
        response = self.web_client.conversations_open(users=self.testbot_userid)
        self.dm_chan = response['channel']['id']

    def _is_testbot_online(self):
        response = self.web_client.users_getPresence(user=self.testbot_userid)
        return response['presence'] == 'active'

    def _has_uploaded_file(self, name, start=None, end=None):
        ts_from = start or self._start_ts
        ts_to = end or time.time()
        response = self.web_client.files_list(
            user=self.testbot_userid, ts_from=ts_from, ts_to=ts_to)
        for f in response.get('files', []):
            if f['name'] == name:
                return True
        return False

    def _has_reacted(self, emojiname):
        for msg in self._channel_messages(self.cm_chan):
            reactions = msg.get('reactions', [])
            for reaction in reactions:
                if reaction['name'] == emojiname and self.testbot_userid in reaction.get('users', []):
                    return True
        return False

    def _join_test_channel(self):
        response = self.web_client.conversations_join(channel=self.test_channel)
        self.cm_chan = response['channel']['id']
        self._invite_testbot_to_channel()

        private_channels = self.web_client.conversations_list(
            types='private_channel').get('channels', [])
        for private_channel in private_channels:
            if self.test_private_channel == private_channel['name']:
                self.gm_chan = private_channel['id']
                self._invite_testbot_to_private_channel(private_channel)
                break
        else:
            raise RuntimeError('Have you created the private channel {} for testing?'.format(
                self.test_private_channel))

    def _invite_testbot_to_channel(self):
        info = self.web_client.conversations_info(channel=self.cm_chan)
        if self.testbot_userid not in info['channel'].get('members', []):
            self.web_client.conversations_invite(channel=self.cm_chan, users=self.testbot_userid)

    def _invite_testbot_to_private_channel(self, private_channel):
        info = self.web_client.conversations_info(channel=self.gm_chan)
        if self.testbot_userid not in info['channel'].get('members', []):
            self.web_client.conversations_invite(channel=self.gm_chan, users=self.testbot_userid)

    def _is_bot_message(self, msg):
        if msg.get('type') != 'message':
            return False
        return msg.get('user') == self.testbot_userid \
            or msg.get('username') == self.testbot_username

    def clear_events(self):
        self._start_ts = time.time()
