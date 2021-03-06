from sqlite3 import Timestamp
import slack
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, Response,jsonify
from slackeventsapi import SlackEventAdapter
import string
from datetime import datetime, timedelta
import time
from markupsafe import escape

load_dotenv()

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(
    os.environ['SIGNING_SECRET'], '/slack/events', app)

client = slack.WebClient(token=os.environ['SLACK_TOKEN'])
BOT_ID = client.api_call("auth.test")['user_id']

reaction_messages = {}


class ReactionMessage:
    START_TEXT = {
        'type': 'section',
        'text': {
            'type': 'mrkdwn',
            'text': (
                '*Your message:* \n\n'
            )
        }
    }

    START_REACTION = {
        'type': 'section',
        'text': {
            'type': 'mrkdwn',
            'text': (
                '*Your reaction list:* \n\n'
            )
        }
    }

    DIVIDER = {'type': 'divider'}

    def __init__(self, event):
        user_id = event.get('user')
        channel_id = event.get('channel')
        self.user_dm = f'@{user_id}'
        self.channel = channel_id
        self.timestamp = ''
        self.text = event.get('text')
        self.thread_ts = event.get('ts')

    def get_message(self):
        return {
            'ts': self.timestamp,
            'channel': self.user_dm,
            'blocks': [
                self.START_TEXT,
                self._get_text(),
                self.DIVIDER,
                self.START_REACTION,
                self._get_reaction_task()
            ]
        }

    def _get_text(self):
        return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': self.text}}

    def _get_reaction_task(self):
        reactions = client.reactions_get(
            channel=self.channel,full=True, timestamp=self.thread_ts)
        get_reaction_messages = reactions.get('message')

        if 'reactions' in get_reaction_messages:
            text = ''
            for reaction in get_reaction_messages['reactions']:
                text += f':{reaction["name"]}: Total: {reaction["count"]}, reacted by: \n'
                for user in reaction['users']:
                    text += f'<@{user}>'
                text += '\n'
            return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}
        else:
            return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': 'No reactions'}}


def send_reaction_message(event):
    channel = event.get('channel')
    user = event.get('user')
    ts = event.get('ts')
    
    if f'@{user}' not in reaction_messages:
        reaction_messages[f'@{user}'] = {}
        reaction_messages[f'@{user}'][channel] = {}

    else:
        if channel not in reaction_messages[f'@{user}']:
            reaction_messages[f'@{user}'][channel] = {}

    reaction = ReactionMessage(event)
    message = reaction.get_message()
    response = client.chat_postMessage(**message)
    reaction.timestamp = response['ts']
    reaction.user_dm = response['channel']

    reaction_messages[f'@{user}'][channel][ts] = reaction
    return


@ slack_event_adapter.on('reaction_added')
def reaction(payload):
    event = payload.get('event', {})
    channel_id = event.get('item', {}).get('channel')
    user_id = event.get('item_user')
    ts = event.get('item', {}).get('ts')
    if f'@{user_id}' not in reaction_messages:
        return
    else:
        if channel_id not in reaction_messages[f'@{user_id}']:
            return
        else:
            if ts not in reaction_messages[f'@{user_id}'][channel_id]:
                return

    reaction = reaction_messages[f'@{user_id}'][channel_id][ts]
    message = reaction.get_message()

    updated_message = client.chat_update(**message)
    reaction.timestamp = updated_message['ts']


@ slack_event_adapter.on('reaction_removed')
def reaction_removed(payload):
    event = payload.get('event', {})
    channel_id = event.get('item', {}).get('channel')
    user_id = event.get('item_user')
    ts = event.get('item', {}).get('ts')

    if f'@{user_id}' not in reaction_messages:
        return
    else:
        if channel_id not in reaction_messages[f'@{user_id}']:
            return
        else:
            if ts not in reaction_messages[f'@{user_id}'][channel_id]:
                return

    reaction = reaction_messages[f'@{user_id}'][channel_id][ts]
    message = reaction.get_message()
    updated_message = client.chat_update(**message)
    reaction.timestamp = updated_message['ts']


@ slack_event_adapter.on('app_mention')
def mention(payload):
    event = payload.get('event', {})
    user_id = event.get('user')
    channel_id = event.get('channel')
    ts = event.get('ts')

    if user_id != None and BOT_ID != user_id:
        if f'@{user_id}' not in reaction_messages:
            send_reaction_message(event)
        else:
            if channel_id not in reaction_messages[f'@{user_id}']:
                send_reaction_message(event)
            else:
                if ts not in reaction_messages[f'@{user_id}'][channel_id]:
                    send_reaction_message(event)

@app.route('/reaction/channelid/<channelId>/timestamp/<timestamp>')
def getReaction(channelId,timestamp):
    req = client.reactions_get(
            channel=channelId,full=True, timestamp=timestamp)
    get_reaction_messages = req.get('message')
    reactions = get_reaction_messages['reactions']
    data_list=[]
    for reaction in reactions:
        data = {}
        user_names=[]
        data['count'] = reaction.get('count')
        data['reaction_names'] = reaction.get('name')
        for user in reaction.get('users'):
            req = client.users_info(user=user)
            user_names.append(req['user']['profile']['real_name'])
        data['user'] = user_names   
        data_list.append(data)
    print(data_list)
    return jsonify(data_list)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
