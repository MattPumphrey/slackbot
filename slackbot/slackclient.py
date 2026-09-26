# -*- coding: utf-8 -*-

import os
import logging
from urllib.parse import urlparse

from slack_sdk import WebClient

from slackbot.utils import to_utf8

logger = logging.getLogger(__name__)


def webapi_generic_list(web_client, method_name, response_key):
    """Generic <foo>_list request, where <foo> could be users, conversations,
    etc."""
    ret = []
    next_cursor = None
    while True:
        args = {}
        if next_cursor:
            args['cursor'] = next_cursor
        response = getattr(web_client, method_name)(**args)
        ret.extend(response.get(response_key, []))

        next_cursor = response.get('response_metadata', {}).get('next_cursor')
        if not next_cursor:
            break
        logging.info('Getting next page for %s (%s collected)', method_name, len(ret))
    return ret


class SlackClient(object):
    def __init__(self, token, timeout=None, bot_icon=None, bot_emoji=None, connect=True,
                 rtm_start_args=None):
        self.token = token
        self.bot_icon = bot_icon
        self.bot_emoji = bot_emoji
        self.username = None
        self.domain = None
        self.login_data = None
        self.users = {}
        self.channels = {}
        self.connected = False

        if rtm_start_args is not None:
            logger.warning(
                'rtm_start_args is no longer used now that the bot connects '
                'via Socket Mode; it will be ignored')

        if timeout is None:
            self.web_client = WebClient(token=self.token)
        else:
            self.web_client = WebClient(token=self.token, timeout=timeout)

        if connect:
            self.connect()

    def connect(self):
        reply = self.web_client.auth_test()
        self.parse_slack_login_data(reply)
        self.connected = True

    def list_users(self):
        return webapi_generic_list(self.web_client, 'users_list', 'members')

    def list_channels(self):
        return webapi_generic_list(self.web_client, 'conversations_list', 'channels')

    def parse_slack_login_data(self, auth_data):
        domain = urlparse(auth_data.get('url', '')).hostname or ''
        domain = domain.split('.')[0]
        self.login_data = {
            'self': {'id': auth_data['user_id'], 'name': auth_data['user']},
            'team': {'id': auth_data.get('team_id'), 'domain': domain},
        }
        self.domain = domain
        self.username = self.login_data['self']['name']
        self.parse_user_data(self.list_users())
        self.parse_channel_data(self.list_channels())

    def parse_channel_data(self, channel_data):
        self.channels.update({c['id']: c for c in channel_data})

    def parse_user_data(self, user_data):
        self.users.update({u['id']: u for u in user_data})

    def upload_file(self, channel, fname, fpath, comment):
        fname = fname or to_utf8(os.path.basename(fpath))
        self.web_client.files_upload_v2(
            channel=channel,
            file=fpath,
            filename=fname,
            initial_comment=comment)

    def upload_content(self, channel, fname, content, comment):
        self.web_client.files_upload_v2(
            channel=channel,
            content=content,
            filename=fname,
            initial_comment=comment)

    def send_message(self, channel, message, attachments=None, as_user=True, thread_ts=None):
        self.web_client.chat_postMessage(
            channel=channel,
            text=message,
            username=self.login_data['self']['name'],
            icon_url=self.bot_icon,
            icon_emoji=self.bot_emoji,
            attachments=attachments,
            as_user=as_user,
            thread_ts=thread_ts)

    def get_channel(self, channel_id):
        return Channel(self, self.channels[channel_id])

    def open_dm_channel(self, user_id):
        return self.web_client.conversations_open(users=user_id)['channel']['id']

    def find_channel_by_name(self, channel_name):
        for channel_id, channel in self.channels.items():
            try:
                name = channel['name']
            except KeyError:
                name = self.users[channel['user']]['name']
            if name == channel_name:
                return channel_id

    def get_user(self, user_id):
        return self.users.get(user_id)

    def find_user_by_name(self, username):
        for userid, user in self.users.items():
            if user['name'] == username:
                return userid

    def react_to_message(self, emojiname, channel, timestamp):
        self.web_client.reactions_add(
            name=emojiname,
            channel=channel,
            timestamp=timestamp)


class Channel(object):
    def __init__(self, slackclient, body):
        self._body = body
        self._client = slackclient

    def __eq__(self, compare_str):
        name = self._body['name']
        cid = self._body['id']
        return name == compare_str or "#" + name == compare_str or cid == compare_str

    def upload_file(self, fname, fpath, initial_comment=''):
        self._client.upload_file(
            self._body['id'],
            to_utf8(fname),
            to_utf8(fpath),
            to_utf8(initial_comment)
        )

    def upload_content(self, fname, content, initial_comment=''):
        self._client.upload_content(
            self._body['id'],
            to_utf8(fname),
            to_utf8(content),
            to_utf8(initial_comment)
        )
