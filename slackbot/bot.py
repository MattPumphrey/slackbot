# -*- coding: utf-8 -*-
import logging
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slackbot import settings
from slackbot.manager import PluginsManager
from slackbot.slackclient import SlackClient
from slackbot.dispatcher import MessageDispatcher

logger = logging.getLogger(__name__)


class Bot(object):
    def __init__(self):
        self._client = SlackClient(
            settings.API_TOKEN,
            timeout=settings.TIMEOUT if hasattr(settings,
                                                'TIMEOUT') else None,
            bot_icon=settings.BOT_ICON if hasattr(settings,
                                                  'BOT_ICON') else None,
            bot_emoji=settings.BOT_EMOJI if hasattr(settings,
                                                    'BOT_EMOJI') else None
        )
        self._plugins = PluginsManager()
        self._dispatcher = MessageDispatcher(self._client, self._plugins,
                                             settings.ERRORS_TO)
        self._app = App(token=settings.API_TOKEN)
        self._register_listeners()

    def _register_listeners(self):
        @self._app.event('message')
        def _handle_message(event):
            self._dispatcher.on_message_event(event)

        def _handle_channel_event(event):
            channel = event.get('channel')
            if channel:
                self._dispatcher.on_channel_event(channel)

        for event_type in ('channel_created', 'channel_rename',
                           'group_joined', 'group_rename', 'im_created'):
            self._app.event(event_type)(_handle_channel_event)

        def _handle_user_event(event):
            user = event.get('user')
            if user:
                self._dispatcher.on_user_event(user)

        for event_type in ('team_join', 'user_change'):
            self._app.event(event_type)(_handle_user_event)

    def run(self):
        if not getattr(settings, 'APP_TOKEN', None):
            raise ValueError(
                'settings.APP_TOKEN (or the SLACKBOT_APP_TOKEN env var) is '
                'required to connect via Socket Mode. Enable Socket Mode '
                'for your Slack app and generate an app-level token with '
                'the connections:write scope.')

        self._plugins.init_plugins()
        logger.info('connecting to slack via socket mode')
        SocketModeHandler(self._app, settings.APP_TOKEN).start()


def respond_to(matchstr, flags=0):
    def wrapper(func):
        PluginsManager.commands['respond_to'][
            re.compile(matchstr, flags)] = func
        logger.info('registered respond_to plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper


def listen_to(matchstr, flags=0):
    def wrapper(func):
        PluginsManager.commands['listen_to'][
            re.compile(matchstr, flags)] = func
        logger.info('registered listen_to plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper


# def default_reply(matchstr=r'^.*$', flags=0):
def default_reply(*args, **kwargs):
    """
    Decorator declaring the wrapped function to the default reply hanlder.

    May be invoked as a simple, argument-less decorator (i.e. ``@default_reply``) or
    with arguments customizing its behavior (e.g. ``@default_reply(matchstr='pattern')``).
    """
    invoked = bool(not args or kwargs)
    matchstr = kwargs.pop('matchstr', r'^.*$')
    flags = kwargs.pop('flags', 0)

    if not invoked:
        func = args[0]

    def wrapper(func):
        PluginsManager.commands['default_reply'][
            re.compile(matchstr, flags)] = func
        logger.info('registered default_reply plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper if invoked else wrapper(func)
