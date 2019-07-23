
import os

CLIENT_ID = os.getenv('POL_ID', '')
CLIENT_SECRET = os.getenv('POL_SECRET', '')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN', 'NOT SPECIFIED')

class FakeCursor:
  def execute(self, cmd):
    # storage of org,refresh_token,access_token sets not implemented yet
    raise Exception('Need to implement DB storage and token refresh for prod')

class TokenManager:

  def __init__(self):
    self.cur = FakeCursor()
    return

  def save_org_token(self, org, access, refresh):
    # clear existing entry for org if present.
    cmd = "delete from %s where org = %d" % (TABLE_NAME, org)
    self.cur.execute(cmd)
    cmd = """insert into %s (org, accessToken, refreshToken) values (%s, "%s", "%s")""" % (TABLE_NAME, org, access, refresh)
    self.cur.execute(cmd)

  def get_testing_token(self):
    return ACCESS_TOKEN

  def get_token(self, org):
    cmd = "select * from %s where org = %d limit 1"
    self.cur.execute(cmd)
    entry = self.cur.fetchone()
    return {
        "org": entry[0],
        "accessToken": entry[1],
        "refreshToken": entry[2]
    }

  def post_token_data(self, code):
    return {
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "code": code,
        "grantType": "authorization_code"
    }

  def post_refresh_data(self, refresh):
    return {
        "clientId": CLIENT_ID,
        "clientSecret": CLIENT_SECRET,
        "refreshToken": refresh,
        "grantType": "refresh_token"
    }
