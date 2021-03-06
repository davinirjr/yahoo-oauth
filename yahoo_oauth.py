"""
BaseOAuth is inspired from Darren Kempiners YahooAPI https://github.com/dkempiners/python-yahooapi/blob/master/yahooapi.py
"""
from __future__ import absolute_import

try:
    input = raw_input
except NameError:
    pass

import pdb
import json
import time
import logging
import webbrowser

import base64

from rauth import OAuth1Service, OAuth2Service
from rauth.utils import parse_utf8_qsl

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s %(levelname)s] [%(name)s.%(module)s.%(funcName)s] %(message)s")
logging.getLogger('yahoo-oauth')


services = {
    'oauth1': dict(
        SERVICE = OAuth1Service,
        REQUEST_TOKEN_URL = "https://api.login.yahoo.com/oauth/v2/get_request_token",
        ACCESS_TOKEN_URL = "https://api.login.yahoo.com/oauth/v2/get_token",
        AUTHORIZE_TOKEN_URL = "https://api.login.yahoo.com/oauth/v2/request_auth"
    ),
    'oauth2': dict(
        SERVICE = OAuth2Service,
        AUTHORIZE_TOKEN_URL = "https://api.login.yahoo.com/oauth2/request_auth",
        ACCESS_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
    )
}
CALLBACK_URI = 'oob'


def json_write_data(json_data, filename):
    """Write json data into a file
    """
    with open(filename, 'w') as fp:
        json.dump(json_data, fp, indent=4, sort_keys=True, ensure_ascii=False)
        return True
    return False

def json_get_data(filename):
    """Get data from json file
    """
    with open(filename) as fp:
        json_data = json.load(fp)
        return json_data

    return False


class BaseOAuth(object):
    """
    """
    def __init__(self, oauth_version, consumer_key, consumer_secret, **kwargs):
        """
        consumer_key : client key
        consumer_secret : client secret
        access_token : access token
        access_token_secret : access token secret
        from_file : file containing the credentials
        """
        self.oauth_version = oauth_version
        
        if kwargs.get('from_file'):
            logging.debug("Checking ")
            self.from_file = kwargs.get('from_file')
            json_data = json_get_data(self.from_file)
            vars(self).update(json_data)
        else:
            self.consumer_key = consumer_key
            self.consumer_secret = consumer_secret

        vars(self).update(kwargs)

        self.oauth_version = oauth_version
        self.callback_uri = vars(self).get('callback_uri',CALLBACK_URI)

        # Init OAuth
        if self.oauth_version == 'oauth1':
            service_params = {
                'consumer_key': self.consumer_key,
                'consumer_secret' : self.consumer_secret,
                'request_token_url': services[self.oauth_version]['REQUEST_TOKEN_URL']
            }
        else:
            service_params = {
                'client_id': self.consumer_key,
                'client_secret': self.consumer_secret
            }

        service_params.update({
            'name' : 'yahoo',
            'access_token_url' : services[self.oauth_version]['ACCESS_TOKEN_URL'],
            'authorize_url' : services[self.oauth_version]['AUTHORIZE_TOKEN_URL'],
            'base_url': vars(self).get('base_url',None)
        })

        # Defining oauth service
        self.oauth = services[oauth_version]['SERVICE'](**service_params)
        
        if vars(self).get('access_token') and vars(self).get('access_token_secret') and vars(self).get('session_handle'):
            if not self.token_is_valid():
                json_data.update(self.refresh_access_token())
        elif vars(self).get('access_token') and vars(self).get('token_type') and vars(self).get('refresh_token'):
            if not self.token_is_valid():
                json_data.update(self.refresh_access_token())
        else:
            json_data.update(self.handler()) 
        
        # Getting session
        if self.oauth_version == 'oauth1':
            self.session = self.oauth.get_session((self.access_token, self.access_token_secret))
        else:
            self.session = self.oauth.get_session(token=self.access_token)

        json_write_data(json_data, self.from_file)


    def handler(self,):
        """* get request token if OAuth1
            * Get user authorization
            * Get access token
        """

        if self.oauth_version == 'oauth1':
            request_token, request_token_secret = self.oauth.get_request_token(params={'oauth_callback': self.callback_uri})
            logging.debug("REQUEST_TOKEN = {0}\n REQUEST_TOKEN_SECRET = {1}\n".format(request_token, request_token_secret))
            authorize_url = self.oauth.get_authorize_url(request_token)
        else:
            authorize_url = self.oauth.get_authorize_url(client_secret=self.consumer_secret, redirect_uri=self.callback_uri, response_type='code')

        logging.debug("AUTHORISATION URL : {0}".format(authorize_url))
        # Open authorize_url
        webbrowser.open(authorize_url)
        self.verifier = input("Enter verifier : ")

        self.token_time = time.time()
    
        credentials = {'token_time': self.token_time}
        
        if self.oauth_version == 'oauth1':
            raw_access = self.oauth.get_raw_access_token(request_token, request_token_secret, params={"oauth_verifier": verifier})
            parsed_access = parse_utf8_qsl(raw_access.content)

            self.access_token = parsed_access['oauth_token']
            self.access_token_secret = parsed_access['oauth_token_secret']
            self.session_handle = parsed_access['oauth_session_handle']
            
            # Updating credentials 
            credentials.update({
                'access_token': self.access_token,
                'access_token_secret': self.access_token_secret,
                'session_handle': self.session_handle
            })
        else:
            # Building headers 
            headers = self.generate_oauth2_headers()
            # Getting access token
            raw_access = self.oauth.get_raw_access_token(data={"code": self.verifier, 'redirect_uri': self.callback_uri,'grant_type':'authorization_code'}, headers=headers)
            #parsed_access = parse_utf8_qsl(raw_access.content.decode('utf-8'))
            credentials.update(self.oauth2_access_parser(raw_access))
                    
        return credentials

    def generate_oauth2_headers(self):
        """Generates header for oauth2
        """
        encoded_credentials = base64.b64encode(('{0}:{1}'.format(self.consumer_key,self.consumer_secret)).encode('utf-8'))
        headers={'Authorization':'Basic {0}'.format(encoded_credentials.decode('utf-8'))}

        return headers

    def oauth2_access_parser(self, raw_access):
        """Parse oauth2 access
        """
        parsed_access = json.loads(raw_access.content.decode('utf-8'))
        self.access_token = parsed_access['access_token']
        self.token_type = parsed_access['token_type']
        self.refresh_token = parsed_access['refresh_token']

        credentials = {
            'access_token': self.access_token,
            'token_type': self.token_type,
            'refresh_token': self.refresh_token
        }
        
        return credentials

    def refresh_access_token(self,):
        """Refresh access token
        """
        logging.debug("REFRESHING TOKEN")
        self.token_time = time.time()
        credentials = {
            'token_time': self.token_time
        }

        if self.oauth_version == 'oauth1':
            self.access_token, self.access_token_secret = self.oauth.get_access_token(self.access_token, self.access_token_secret, params={"oauth_session_handle": self.session_handle})
            credentials.update({
                'access_token': self.access_token,
                'access_token_secret': self.access_token_secret,
                'session_handle': self.session_handle,
                'token_time': self.token_time
            })
        else:
            headers = self.generate_oauth2_headers()

            raw_access = self.oauth.get_raw_access_token(data={"refresh_token": self.refresh_token, 'redirect_uri': self.callback_uri,'grant_type':'refresh_token'}, headers=headers)
            credentials.update(self.oauth2_access_parser(raw_access))            

        return credentials

    def token_is_valid(self,):
        """Check the validity of the token :3600s
        """
        elapsed_time = time.time() - self.token_time
        logging.debug("ELAPSED TIME : {0}".format(elapsed_time))
        if elapsed_time > 3540: # 1 minute before it expires
            logging.debug("TOKEN HAS EXPIRED")
            return False

        logging.debug("TOKEN IS STILL VALID")
        return True


class OAuth1(BaseOAuth):
    """Class handling OAuth v1
    """

    def __init__(self, consumer_key, consumer_secret, **kwargs):
        
        super(OAuth1, self).__init__('oauth1', consumer_key, consumer_secret, **kwargs)


class OAuth2(BaseOAuth):
    """Calss handling OAuth v2
    """

    def __init__(self, consumer_key, consumer_secret, **kwargs):
       
        super(OAuth2, self).__init__('oauth2', consumer_key, consumer_secret, **kwargs)

     
