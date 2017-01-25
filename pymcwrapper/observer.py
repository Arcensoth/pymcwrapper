import abc
from queue import Queue

import watchdog.events
import watchdog.observers

from pymcwrapper.event import Event


class DirectoryObserverFileChangeEvent(Event):
    def __init__(self, filepath: str):
        self._filepath = filepath

    @property
    def filepath(self):
        return self._filepath


class CustomFileSystemEventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, event_queue: Queue):
        self._event_queue = event_queue

    def on_created(self, event: watchdog.events.FileCreatedEvent):
        self._event_queue.put(DirectoryObserverFileChangeEvent(event.src_path))

    def on_modified(self, event: watchdog.events.FileModifiedEvent):
        self._event_queue.put(DirectoryObserverFileChangeEvent(event.src_path))


class Observer(abc.ABC):
    @abc.abstractmethod
    def start(self):
        """ Start the observer thread. """

    @abc.abstractmethod
    def stop(self):
        """ Stop the observer thread. """

    @abc.abstractmethod
    def join(self):
        """ Join with the observer thread. """


class DirectoryObserver(Observer):
    def __init__(self, event_queue: Queue, path: str, recursive: bool):
        super().__init__()
        self._event_queue = event_queue
        self._path = path
        self._recursive = recursive

        self._thread = watchdog.observers.Observer()
        self._thread.schedule(CustomFileSystemEventHandler(self._event_queue), self._path, recursive=self._recursive)

    def start(self):
        self._thread.start()

    def stop(self):
        self._thread.stop()

    def join(self):
        self._thread.join()
