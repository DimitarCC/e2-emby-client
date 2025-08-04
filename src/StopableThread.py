import threading

class StoppableThread(threading.Thread):
    def __init__(self, target, args=(), kwargs=None):
        super().__init__()
        self._stop_event = threading.Event()
        self._target = target
        self._args = args
        self._kwargs = kwargs if kwargs else {}

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    def run(self):
        # Inject the stop check into the target function
        self._target(self, *self._args, **self._kwargs)