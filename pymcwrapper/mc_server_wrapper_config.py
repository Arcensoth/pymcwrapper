DEFAULT_PROGRAM = 'java -Xmx1024M -Xms1024M -jar minecraft_server.jar nogui'


class MCServerWrapperConfig(object):
    def __init__(self, **options):
        self.program = options.pop('program', DEFAULT_PROGRAM)
        self.jobs = options.pop('jobs', [])
        self.observers = options.pop('observers', [])
