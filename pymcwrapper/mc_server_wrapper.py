import importlib
import os
import threading
import traceback
from queue import Queue
from subprocess import Popen, PIPE
from typing import List

import yaml

from pymcwrapper.event import ExitEvent, InputEvent
from pymcwrapper.job import CommandSequenceJobEvent, Job, CommandSequenceJob
from pymcwrapper.mc_server_wrapper_config import MCServerWrapperConfig
from pymcwrapper.observer import DirectoryObserverFileChangeEvent, Observer, DirectoryObserver

FMT_RESET = '\033[0m'
FMT_RED = '\033[31m'
FMT_YELLOW = '\033[33m'
FMT_BLUE = '\033[34m'


class MCServerWrapper(object):
    EXIT_TOKENS = {'exit', 'x'}

    def __init__(self, config: MCServerWrapperConfig):
        self.config = config

        self._event_queue = Queue()

        self._jobs: List[Job] = []
        for raw_job in self.config.jobs:
            self._jobs.append(self._make_job(self._event_queue, raw_job))

        self._observers: List[Observer] = []
        for raw_observer in self.config.observers:
            self._observers.append(self._make_observer(self._event_queue, raw_observer))

        self._event_handler_map = {
            InputEvent.__name__: self._handle_input_event,
            CommandSequenceJobEvent.__name__: self._handle_command_sequence_job_event,
            DirectoryObserverFileChangeEvent.__name__: self._handle_directory_observer_file_change_event,
            ExitEvent.__name__: self._handle_exit_event}

        self._cmd_map = {
            'start': self._parse_start_command,
            'restart': self._parse_restart_command,
            'echo': self._parse_echo_command,
            'send': self._parse_send_command,
            '>': self._parse_send_command,
            'load': self._parse_load_command,
            'run': self._parse_run_command}

        self._server_input_lock = threading.Lock()

        self._event_queue_thread = threading.Thread(target=self._loop_event_queue)
        self._input_thread = threading.Thread(target=self._loop_input)

        self._server_process = None
        """ :type: Popen """

        self._server_output_thread = None
        """ :type: Thread """

    @staticmethod
    def _make_job(event_queue: Queue, raw_job: dict) -> Job:
        job_type = raw_job['job_type']

        if job_type == 'command_sequence':
            title = raw_job['title']
            delay = raw_job['delay']
            index = raw_job.get('index', 0)
            groups = raw_job['groups']
            return CommandSequenceJob(event_queue, title, delay, index, groups)

        else:
            raise ValueError('Invalid job type: ' + job_type)

    @staticmethod
    def _make_observer(event_queue: Queue, raw_observer: dict) -> Observer:
        observer_type = raw_observer['observer_type']

        if observer_type == 'directory':
            path = raw_observer['path']
            recursive = raw_observer.get('recursive', False)
            return DirectoryObserver(event_queue, path, recursive)

        else:
            raise ValueError('Invalid observer type: ' + observer_type)

    def _loop_event_queue(self):
        while True:
            event = self._event_queue.get()
            event_name = type(event).__name__
            handler_method = self._event_handler_map.get(event_name)

            if not handler_method:
                self._print_warning(f'Ignoring unknown event: {event}')
                continue

            try:
                if handler_method(event):
                    break

            except Exception as e:
                self._print_error('Event resulted in an error:')
                etb = traceback.extract_tb(e.__traceback__)
                fl = traceback.format_list(etb)
                for item in fl:
                    self._print_color(item, color_fmt=FMT_RED, newline=False)
                self._print_color(e.args[0], color_fmt=FMT_RED)

        self._print('Wrapper has stopped.')

    def _loop_input(self):
        while True:
            inp = input().strip()
            if inp in self.EXIT_TOKENS:
                self.exit()
                break
            else:
                self._event_queue.put(InputEvent(inp))

    def _loop_server_output(self):
        for line in self._server_process.stdout:
            self._print_server(line.rstrip())

    def _is_server_running(self) -> bool:
        if self._server_output_thread:
            return self._server_output_thread.isAlive()
        return False

    def _write_server(self, text):
        if self._is_server_running():
            self._server_input_lock.acquire()
            self._server_process.stdin.write(text)
            self._server_process.stdin.flush()
            self._server_input_lock.release()
        else:
            self._print_error('Server is not running!')

    def _handle_input_event(self, event: InputEvent):
        line = event.to_input.rstrip()
        tokens = line.split(maxsplit=1)

        if not tokens:
            return

        method = self._cmd_map.get(tokens[0])

        if method:
            method(tokens[1] if len(tokens) > 1 else '')
        else:
            self.send(line)

    def _handle_command_sequence_job_event(self, event: CommandSequenceJobEvent):
        self._print('Running command sequence:', event.title)
        self.pipe(event.text)

    def _handle_directory_observer_file_change_event(self, event: DirectoryObserverFileChangeEvent):
        self.load_file(event.filepath)

    def _handle_exit_event(self, event: ExitEvent):
        self._print('Stopping wrapper...')

        # Join with the input thread, which should be finished after seeing the exit token.
        self._print('Cleaning up input...')
        self._input_thread.join()

        # Stop the server, if not already running.
        if self._is_server_running():
            self.stop_server()

        # Clean up all jobs.
        if self._jobs:
            self._print(f'Cleaning up {len(self._jobs)} job(s)...')
        for job in self._jobs:
            job.stop()
            job.join()

        # Clean up all observers.
        if self._observers:
            self._print(f'Cleaning up {len(self._observers)} observer(s)...')
        for observer in self._observers:
            observer.stop()
            observer.join()

        # Return true so the calling event thread will finish.
        return True

    def _print(self, *args, prefix: str = '', suffix: str = '', newline: bool = True):
        message = prefix + ' '.join([str(arg) for arg in args]) + suffix
        print(message, end=None if newline else '', flush=not newline)

    def _print_color(self, *args, color_fmt=FMT_RESET, **kwargs):
        self._print(*args, **kwargs, prefix=color_fmt, suffix=FMT_RESET)

    def _print_error(self, *args, **kwargs):
        self._print_color(*args, **kwargs, color_fmt=FMT_RED)

    def _print_warning(self, *args, **kwargs):
        self._print_color(*args, **kwargs, color_fmt=FMT_YELLOW)

    def _print_server(self, *args, **kwargs):
        self._print_color(*args, **kwargs, color_fmt=FMT_BLUE)

    def _parse_echo_command(self, argline: str):
        self.echo(argline)

    def _parse_send_command(self, argline: str):
        self.send(argline)

    def _parse_start_command(self, argline: str):
        self.start_server()

    def _parse_restart_command(self, argline: str):
        self.restart_server()

    def _parse_load_command(self, argline: str):
        self.load(argline)

    def _parse_run_command(self, argline: str):
        self.run(argline)

    def start(self):
        self.start_server()
        self._input_thread.start()
        self._event_queue_thread.start()

        for observer in self._observers:
            observer.start()

        for job in self._jobs:
            job.start()

    def start_server(self):
        if self._is_server_running():
            self._print_error('Server is already running!')
        else:
            self._print('Starting server...')
            self._server_process = Popen(self.config.program.split(), stdin=PIPE, stdout=PIPE, universal_newlines=True)
            self._server_output_thread = threading.Thread(target=self._loop_server_output)
            self._server_output_thread.start()

    def restart_server(self):
        self.stop_server()
        self.start_server()

    def stop_server(self):
        if self._is_server_running():
            self._print('Stopping server...')
            self.send('stop')
            self._print('Waiting for server to stop...')
            self._server_process.wait()
            self._print('Cleaning up server...')
            self._server_output_thread.join()
            self._print('Server has stopped.')
        else:
            self._print_error('Server is not running!')

    def join(self):
        self._event_queue_thread.join()

    def exit(self):
        self._event_queue.put(ExitEvent())

    def echo(self, message: str):
        self._print(message)

    def pipe(self, text: str):
        self._write_server(text)

    def send(self, text: str):
        self.pipe(text + '\n')

    def load_file(self, path: str):
        self._print('Loading file:', path)
        with open(path) as fp:
            self.pipe(fp.read())

    def load_dir(self, path: str):
        self._print('Loading directory:', path)
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            self.load_file(filepath)

    def load(self, path: str):
        if os.path.isfile(path):
            self.load_file(path)
        elif os.path.isdir(path):
            self.load_dir(path)
        else:
            self._print_error('Cannot load invalid path:', path)

    def run(self, argline: str):
        tokens = argline.split(maxsplit=1)
        module_name = tokens[0]
        params = yaml.load(tokens[1]) if len(tokens) > 1 else {}

        try:
            module = importlib.import_module(module_name)
            run_fn = getattr(module, 'run')

            self._print_warning(f'Running procedure {module_name} with parameters: {params}')

            for command in run_fn(**params):
                self.send(str(command))

        except ModuleNotFoundError:
            self._print_error(f'No such procedure: {module_name}')

        except AttributeError:
            self._print_error(f'Procedure has no "run" method: {module_name}')
