import os
import requests
import re 
import json

MONKEY_LEARN_KEY = os.getenv('MONKEY_LEARN_KEY', None)
print('monkey', MONKEY_LEARN_KEY)

KEYWORD_URL = "https://api.monkeylearn.com/v3/extractors/ex_YCya9nrn/extract/"
CLASSIFICATION_URL = "https://api.monkeylearn.com/v3/classifiers/cl_sGdE8hD9/classify/"
SENT_URL = "https://api.monkeylearn.com/v3/classifiers/cl_pi3C7JiL/classify/"


def get_monkey_header(token):
  return { "Authorization": "Token %s" % token, "Content-Type": 'application/json' }

def get_body(message):
  if 'body' in message:
    return message['body']
  return ''

def get_sent_polarity(sents):
  score = 0
  for s in sents:
    tag = s['tag_name']
    conf = s['confidence']
    if tag == 'Positive':
      score += conf
    elif tag == 'Negative':
      score -= conf

  return score

# https://app.monkeylearn.com/main/explore/
class MonkeyLearn:
    def __init__(self):
      self.key = MONKEY_LEARN_KEY

    def is_enabled(self):
      return self.key is not None

    def get_keyword_extractions(self, text):
      body = {"data":[text]}
      response = requests.post(KEYWORD_URL, data=json.dumps(body), headers=get_monkey_header(self.key))
      if response.status_code != 200:
        print('error getting keywords', response.reason)
        return []

      data = response.json()
      res = data[0]['extractions']
      return res
    
    def get_classification_extractions(self, text):
      body = {"data":[text]}
      response = requests.post(CLASSIFICATION_URL, data=json.dumps(body), headers=get_monkey_header(self.key))
      if response.status_code != 200:
        print('error getting classification', response.reason)
        return []

      data = response.json()
      res = data[0]['classifications']
      return res

    def get_sentiments(self, messages):
          texts = list(map(get_body, messages))
          body = {"data":texts}
          response = requests.post(SENT_URL, data=json.dumps(body), headers=get_monkey_header(self.key))
          if response.status_code != 200:
            print('error getting sentiments', response.reason)
            return []

          data = response.json()
          classifications = list(map(lambda x: x['classifications'], data))
          res = list(map(get_sent_polarity, classifications))
          return res








