from textblob import TextBlob
import urllib.parse as urlparse
import os
import requests
import re 
import json
# import boto3
from token_manager import TokenManager
from monkey_learn import MonkeyLearn
from drift import Drift

POLARITY_ENV_VAR = os.getenv('POL_ENV', 'qa')


S3_BUCKET = os.getenv('POL_BUCKET', 'test-drift-bucket')
BASE_URL = ("https://driftapi.com", "https://driftapiqa.com")[POLARITY_ENV_VAR == 'qa']

OAUTH_URL = "%s/oauth2/token" % BASE_URL
CONVERSATION_BASE_URL =  "%s/v1/conversations" % BASE_URL
CONTACT_URL = "%s/contacts" % BASE_URL
USER_URL = "%s/users/list" % BASE_URL
TABLE_NAME = "polarity"

EMAIL_WIDTH = 30
MIDDLE_WIDTH = 25
LINE_WIDTH = 99
TEXT_WIDTH = max(LINE_WIDTH - MIDDLE_WIDTH - EMAIL_WIDTH, 0)

def generateHTMLResponse(statusCode, body):
    return {
        "statusCode": statusCode,
        "headers": {
            "Content-Type": "text/html"
        },
        "body": body
    }

def get_drift_header(token):
    return { "Authorization": "Bearer %s" % token, "Content-Type": 'application/json' }

def chat_message(message):
    return 'body' in message and message['type'] == 'chat'

def clean_message(message):
    if 'body' in message:
        text = message['body']
        text = re.sub('<[^<]+?>', '', text)
        message['body'] = text
    return message


class Polarity:

    def __init__(self):
        self.token_manager = TokenManager()
        self.monkey_learn = MonkeyLearn()
        # self.s3 = boto3.resource('s3')
        self.file_bucket = None # self.s3.Bucket(S3_BUCKET)
        self.drift_client = Drift(self.token_manager.get_testing_token())
        with open('success.html', 'r') as f:
            self.success_html = f.read()

    def upload(self, file_name):
        if self.file_bucket:
            data = open(file_name, 'rb') # image file (or binary)
            self.file_bucket.put_object(Key=file_name, Body=data)

    def get_user_map(self, org_id):
        response = requests.get(USER_URL, headers=get_drift_header(self.token_manager.get_testing_token()))
        if response.status_code != 200:
            # TODO: implement error handle
            return {}
        data = response.json()
        users = data['data']

        user_map = {}
        for i, user in enumerate(users):
            user_map[user['id']] = user

        return user_map

    def get_conversation_messages(self, conversation_id):
        url = "%s/conversations/%s/messages" % (BASE_URL, conversation_id)
        response = requests.get(url, headers=get_drift_header(self.token_manager.get_testing_token()))
        print(response.text)
        return response.json()

    def request_token(self, code):
        r = requests.post(OAUTH_URL, data=self.token_manager.post_token_data(code))
        if (r.status_code != 200):
            return generateHTMLResponse(500, "<h3>Error registering:</h3><p>%s</p>" %r.text)

        data = r.json()

        self.drift_client = Drift(data['accessToken'])
        self.token_manager.save_org_token(data['orgId'], data['accessToken'], data['refreshToken'])
        return generateHTMLResponse(200, self.success_html)

    def get_summary_line(self, polarities):
        avg = round(float(sum(polarities)) / len(polarities) * 10, 1)
        last = polarities[-1]
        last_line = ""
        if avg > 0:
            if last > 0:
                last_line = "Good job. Overall positive conversation."
            else:
                last_line = "Was a good conversation, but trailed a bit at the end there. Keep the sentiment upbeat."
        else:
            if last > 0:
                last_line = "Negative overall, but the conversation recovered a bit at the end there."
            else:
                last_line = "Try to keep the conversation more positive to maintain a good impression."

        return "<br/>Average score: %.2f<br/>* %s" % (avg, last_line)
       
    def get_polarity_summary(self, org_id, messages):
        if not messages:
            print('No messages in conversation to analyze')
            return None

        last_message = messages[-1]
        if last_message['type'] == 'private_prompt' and 'Polarity' in last_message['body']:
            print('last message posted was from Polarity, returning')
            return None

        user_map = self.get_user_map(org_id)
        contact_map = {}
        message_bodies = []

        lines = []
        polarities = []

        messages = list(map(clean_message, filter(chat_message, messages)))

        if self.monkey_learn.is_enabled():
            monkey_polarities = self.monkey_learn.get_sentiments(messages)

        for i, message in enumerate(messages):

            text = message['body']
            polarity = 0
            if self.monkey_learn.is_enabled():
                message_bodies.append(text)
                polarity = monkey_polarities[i]
            else:
                blob = TextBlob(text)
                polarity = blob.sentiment.polarity

            mag = int(abs(polarity) * 10)
            if mag == 0:
                # skip neutral message
                continue

            author_id = message['author']['id']
            author_label = 'Site Visitor' 
            # TODO: make this work
            if author_id in user_map:
                author_label = user_map[author_id]['email']
            else:
                url = "%s/%s" % (CONTACT_URL, author_id)
                response = requests.get(url, headers=get_drift_header(self.token_manager.get_testing_token()))
                if response.status_code == 200:
                    data = response.json()
                    author_label = data.get('email', 'Site Visitor')
                    attrs = data['data']['attributes']
                    if 'email' in attrs:
                        visitor_email = attrs['email']
                        if visitor_email:
                            author_label = visitor_email

            polarities.append(polarity)
            mag = int(abs(polarity) * 10)
            # print('polarity', polarity, text)
            bars = mag * "*"
            if polarity < 0:
                graph = "{0:>10}|{1:<10}".format(bars, " ")
            else:
                graph = "{0:>10}|{1:<10}".format(" ", bars)
            text_visible_len = min(len(text), TEXT_WIDTH)
            msg = "{0:<{x}}{1:^{y}}{2:<{z}}".format(author_label, graph, text[:text_visible_len], x=EMAIL_WIDTH, y=MIDDLE_WIDTH, z=TEXT_WIDTH)
            # msg = msg.replace(' ','*')
            lines.append(msg)

        if self.monkey_learn.is_enabled():
            raw_text = ' '.join(message_bodies)
            extractions = self.monkey_learn.get_keyword_extractions(raw_text)
            if extractions:
                keywords = ', '.join(list(filter(lambda x: len(x) < 10, map(lambda x: x['parsed_value'], extractions))))
                keywords_line = "<br/>Keywords: %s" % keywords
                lines.append(keywords_line)

            classifications = self.monkey_learn.get_classification_extractions(raw_text)
            if classifications:
                topics = ', '.join(list(map(lambda x: x['tag_name'], classifications)))
                topics_line = "Topics: %s" % topics
                lines.append(topics_line)

        summary_line = self.get_summary_line(polarities)
        lines.append(summary_line)

        return lines

    def get_sentiment_report(self, org_id, messages):
        report_string = '<h3>Polarity Summary:</h3>Conversation Highlights:<br/>'
        lines = self.get_polarity_summary(org_id, messages)
        if not lines:
            return None
        report_string += "<p style=\"font-family: var(--code-font-family);\">" + "<br/>".join(lines) + "</p>"
        return report_string
    
    # send message with retry
    def send_message(self, org, conversation_id, message):
        # print('sending message\n', org, conversation_id, message)
        # token_obj = self.token_manager.get_token(org)
        url = "%s/%s/messages" % (CONVERSATION_BASE_URL, conversation_id)
        # access_token = token_obj['accessToken']
        access_token = self.token_manager.get_testing_token()
        r = requests.post(url, data=json.dumps(message), headers=get_drift_header(access_token)) 
        if r.status_code != 200:
            print('post message request failed', r.status_code, r.reason)
            # get new token and retry request.
            refresh_token = token_obj['refreshToken']
            r = requests.post(OAUTH_URL, data=self.token_manager.post_refresh_data(refresh_token))
            data = r.json()
            new_access_token = data['accessToken']
            self.token_manager.save_org_token(data['orgId'], new_access_token, data['refreshToken'])
            r = requests.post(url, data=message, headers=get_drift_header(new_access_token))
        print('sent message')

    def create_api_message(self, body):
        return {"body": body, "type": "private_prompt"}