from sr.comp.scorer.app import app
import argparse


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SR Competition Scorer')
    parser.add_argument('compstate',
                        help='Competition state git repository path')
    parser.add_argument('-l', '--local', action='store_true',
                        help='Disable fetch and push')
    parser.add_argument('-u', '--username', help='Username')
    parser.add_argument('-p', '--password', help='Password')
    args = parser.parse_args()

    app.config['COMPSTATE'] = args.compstate
    app.config['COMPSTATE_LOCAL'] = args.local
    if args.username is not None:
        if args.password is None:
            parser.error('--username requires --password')
        app.config['AUTH_USERNAME'] = args.username
        app.config['AUTH_PASSWORD'] = args.password
    elif args.password is not None:
        parser.error('--password requires --username')

    app.run(host='0.0.0.0', port=3000)
