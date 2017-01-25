import argparse
import logging

import yaml

from pymcwrapper.mc_server_wrapper import MCServerWrapper
from pymcwrapper.mc_server_wrapper_config import MCServerWrapperConfig

log = logging.getLogger(__name__)

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('--log', help='log level', default='WARNING')
arg_parser.add_argument('--config', help='configuration file', default='wrapper.yml')
args = arg_parser.parse_args()

try:
    import loggy
    loggy.install(level=args.log)
except:
    logging.basicConfig(level=args.log)

try:
    with open(args.config) as fp:
        options = yaml.load(fp)
except FileNotFoundError:
    log.warning(f'configuration file not found: {args.config}')
    options = {}

config = MCServerWrapperConfig(**options)
wrapper = MCServerWrapper(config=config)

wrapper.start()
wrapper.join()
