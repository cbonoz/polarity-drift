from textblob import TextBlob
import urllib.parse as urlparse
import os
import requests
import json
# import boto3
from token_manager import TokenManager
from drift import Drift

POLARITY_ENV_VAR = os.getenv('POL_ENV', 'qa')
S3_BUCKET = os.getenv('POL_BUCKET', 'test-drift-bucket')
BASE_URL = ("https://driftapi.com", "https://driftapiqa.com")[POLARITY_ENV_VAR == 'qa']

OAUTH_URL = "%s/oauth2/token" % BASE_URL
CONVERSATION_BASE_URL =  "%s/v1/conversations" % BASE_URL
TABLE_NAME = "polarity"

def generateResponse(statusCode, body):
    return {
        "statusCode": statusCode,
        "headers": {
            "Content-Type": "text/html"
        },
        "body": body
    }

def get_drift_header(token):
    return { "Authorization": "Bearer %s" % token, "Content-Type": 'application/json' }

class Polarity:

    def __init__(self):
        self.token_manager = TokenManager()
        # self.s3 = boto3.resource('s3')
        self.file_bucket = None # self.s3.Bucket(S3_BUCKET)
        self.drift_client = None # TODO: use drift-python
        with open('success.html', 'r') as f:
            self.success_html = f.read()

    def upload(self, file_name):
        if self.file_bucket:
            data = open(file_name, 'rb') # image file (or binary)
            self.file_bucket.put_object(Key=file_name, Body=data)

    def get_conversation_messages(self, conversation_id):
        url = "%s/conversations/%s/messages" % (BASE_URL, conversation_id)
        response = requests.get(url, headers=get_drift_header(self.token_manager.get_testing_token()))
        print(response.text)
        return response.json()

    def request_token(self, code):
        r = requests.post(OAUTH_URL, data=self.token_manager.post_token_data(code))
        if (r.status_code != 200):
            return generateResponse(500, "<h3>Error registering:</h3><p>%s</p>" %r.text)

        data = r.json()

        self.drift_client = Drift(data['accessToken'])
        self.token_manager.save_org_token(data['orgId'], data['accessToken'], data['refreshToken'])
        return generateResponse(200, self.success_html)

    def get_summary_line(self, polarities):
        avg = round(sum(polarities) / len(polarities) * 10, 1)
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

        return "<br/><b>Polarity</b> Summary: <br/>Average score: %s<br/>%s" % (avg, last_line)
       
    def get_polarity_summary(self, messages):
        if not messages:
            return "<p>No messages to analyze</p>"

        lines = []
        polarities = []
        for message in messages:
            if 'body' not in message:
                continue
            text = message['body']
            author_id = message['author']['id']

            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            polarities.append(polarity)
            mag = int(round(abs(polarity) * 10, 0))
            # print('polarity', polarity, text)
            bars = mag * "*"
            msg = None
            if polarity < 0:
                msg = "{:<10}{:>10}|".format(author_id, bars)
            else:
                msg = "{:<10}{:10}|{}".format(author_id, "", bars)

            msg = msg.replace(' ','*')
            lines.append(msg)

        summary_line = self.get_summary_line(polarities)
        lines.append(summary_line) 

        return lines

    def get_sentiment_report(self, messages):
        # TODO: identify the parties in the conversation and insert names.
        report_string = "<h3>Polarity:</h3>"
        lines = self.get_polarity_summary(messages)
        report_string += "<p>" + "<br/>".join(lines) + "</p>"

        return report_string
    
    # send message with retry
    def send_message(self, org, conversation_id, message):
        print('sending message\n', org, conversation_id, message)
        # token_obj = self.token_manager.get_token(org)
        url = "%s/%s/messages" % (CONVERSATION_BASE_URL, conversation_id)
        # access_token = token_obj['accessToken']
        access_token = self.token_manager.get_testing_token()
        r = requests.post(url, data=message, headers=get_drift_header(access_token)) 
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

    def generate_drift_message(self, org, message):
        return """{
            "orgId": "%s"
            "body": "%s",
            "type": "private_prompt"
        }""" % (org, message)
