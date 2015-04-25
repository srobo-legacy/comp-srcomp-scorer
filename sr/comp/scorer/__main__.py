from sr.comp.scorer.app import app
import argparse


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SR Competition Scorer')
    parser.add_argument('compstate',
                        help='Competition state git repository path')
    parser.add_argument('-l', '--local', action='store_true',
                        help='Disable fetch and push')
    args = parser.parse_args()

    app.config['COMPSTATE'] = args.compstate
    app.config['COMPSTATE_LOCAL'] = args.local
    app.run(host='0.0.0.0', port=3000)
