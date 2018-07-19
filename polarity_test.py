import json
from polarity import Polarity

p = Polarity()

with open('assets/test_conversation.txt', 'r') as f:
    content = f.read()
    data = json.loads(content)

report = p.get_sentiment_report(data)
print(report)
