import requests

BASE_URL = 'http://127.0.0.1:5000'

routes = [
    '/',
    '/health',
    '/admin-login',
    '/worker-login',
]

def check_route(route):
    try:
        resp = requests.get(BASE_URL + route)
        print(f'{route}: {resp.status_code} {resp.reason}')
    except Exception as e:
        print(f'{route}: ERROR {e}')

if __name__ == '__main__':
    for route in routes:
        check_route(route)
