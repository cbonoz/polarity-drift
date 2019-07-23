import os
from flask import request, jsonify
from flask import Flask
import json

from polarity import Polarity

app = Flask(__name__)

PORT = 3001

# Helper class object for parsing sentiment from conversations
p = Polarity()

@app.route('/hello')
def hello_world():
    return 'Hello, World!'

@app.route('/oauth', methods=['GET'])
def oauth():
    # TODO: save the oauth tokens (access and refresh).
    code = request.args.get("code")
    print('oauth', code)
    response = p.request_token(code)
    return response

# Listen for conversation state change events.
@app.route('/events', methods=['POST'])
def events():
    raw_data = request.data
    data = json.loads(raw_data)
    print('received event', data)
    event_type = data['type']
    if event_type != 'conversation_status_updated':
        return jsonify()
        
    org = data['orgId']
    conversation_closed = data['data']['status'] == 'closed'
    conversation_id = data['data']['conversationId']
    # only fire/generate a report when a conversation is changed to closed status.
    if conversation_closed:
        conv_response = p.get_conversation_messages(conversation_id)
        messages = conv_response['data']['messages']
        report_string = p.get_sentiment_report(messages)
        drift_message = p.generate_drift_message(org, report_string)
        p.send_message(org, conversation_id, drift_message)

    return jsonify()

if __name__ == '__main__':
      app.run(port=PORT)
      print("Polarity server started on port %d!" % PORT)
