from textblob import TextBlob
import psycopg2
import urllib.parse as urlparse
import os
import requests

BASE_URL = "https://driftapi.com"

OAUTH_URL = "%s/oauth2/token" % BASE_URL
CONVERSATION_BASE_URL =  "%s/v1/conversations" % BASE_URL
TABLE_NAME = "polarity"
CLIENT_ID = os.environ['POL_ID']
CLIENT_SECRET = os.environ['POL_SECRET']

# Fully specified postgres database url.
DATABASE_URL = os.environ['POL_DATABASE_URL']
url = urlparse.urlparse(DATABASE_URL)
dbname = url.path[1:]
user = url.username
password = url.password
host = url.hostname
port = url.port


conn =  psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
            )
cur = conn.cursor()

def get_token(org):
    cmd = "select * from %s where org = %d limit 1"
    cur.execute(cmd)
    entry = cur.fetchone()
    return {
        "org": entry[0],
        "accessToken": entry[1],
        "refreshToken": entry[2]
    }

def post_token_data(code):
    return {
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "code": code,
        "grantType": "authorization_code"
    }

def post_refresh_data(refresh):
    return {
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "refreshToken": refresh,
        "grantType": "refresh_token"
    }


def generateResponse(statusCode, body):
    return {
        "statusCode": statusCode,
        "headers": {
            "Content-Type": "text/html"
        },
        "body": body
    }

def get_drift_header(token):
    return { "Authorization": "Bearer %s" % token }

def save_org_token(org, access, refresh):
    # clear existing entry for org if present.
    cmd = "delete from %s where org = %d" % (TABLE_NAME, org)
    cur.execute(cmd)
    cmd = """insert into %s (org, accessToken, refreshToken) values (%s, "%s", "%s")""" % (TABLE_NAME, org, access, refresh)
    cur.execute(cmd)

# text = '''
# The titular threat of The Blob has always struck me as the ultimate movie
# monster: an insatiably hungry, amoeba-like mass able to penetrate
# virtually any safeguard, capable of--as a doomed doctor chillingly
# describes it--"assimilating flesh on contact.
# Snide comparisons to gelatin be damned, it's a concept with the most
# devastating of potential consequences, not unlike the grey goo scenario
# proposed by technological theorists fearful of
# artificial intelligence run rampant.
# '''

class Polarity:

    def __init__(self):
        with open('success.html', 'r') as f:
            self.success_html = f.read()

    def get_conversation_messages(self, token, conversation_id):
        url = "%s/conversations/%s/messages" % (BASE_URL, conversation_id)
        requests.get(url, headers=get_drift_header(token))
        print(response.text)
        return response.json()

    def request_token(self, code):
        r = requests.post(OAUTH_URL, data=post_token_data(code))
        if (r.status_code != 200):
            return generateResponse(500, "<h3>Error registering:</h3><p>%s</p>" %r.text)

        data = r.json()

        save_org_token(data['orgId'], data['accessToken'], data['refreshToken'])
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

        return "<br/><b>Polarity (%.1f): %s</b><br/>" % (avg, last_line)

    def get_polarity_summary(self, messages):
        if not messages:
            return "<p>No messages to analyze</p>"

        lines = []
        polarities = []
        for message in messages:
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

            msg = msg.replace(' ','&nbsp;')
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
        token_obj = get_token(org)
        url = "%s/%s/messages" % (CONVERSATION_BASE_URL, conversation_id)
        access_token = token_obj['accessToken']
        refresh_token = token_obj['refreshToken']
        r = requests.post(url, data=message, headers=get_drift_header(access_token)) 
        if (r.status_code != 200):
            # get new token and retry request.
            r = requests.post(OAUTH_URL, data=post_refresh_data(refresh_token))
            data = r.json()
            new_access_token = data['accessToken']
            save_org_token(data['orgId'], new_access_token, data['refreshToken'])
            r = requests.post(url, data=message, headers=get_drift_header(new_access_token))

        print('send_message', r.status_code, r.text)


    def generate_drift_message(self, org, message):
        return """{
            "orgId": "%s"
            "body": "%s",
            "type": "private_prompt"
        }""" % (org, message)
