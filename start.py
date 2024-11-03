from argparse import ArgumentParser, Namespace
from logging import getLogger, DEBUG, basicConfig
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser


logger = getLogger()
basicConfig(level=DEBUG)


def get_handler(cmd_args: Namespace):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=cmd_args.source, **kwargs)

    return Handler


if __name__ == '__main__':

    parser = ArgumentParser('Starts an HTTP webserver in the given source location.')

    parser.add_argument('-s', '--source', type=str, required=True)
    parser.add_argument('-p', '--port', type=int, default=3000)

    args = parser.parse_args()
    logger.debug(f'Arguments: {args}')

    server = HTTPServer(('', args.port), get_handler(args))
    webbrowser.open(f'http://localhost:{args.port}')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

