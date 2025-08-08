from multiprocessing import Process, Event
from time import sleep


class StoppableWorker:
    def __init__(self, callback, *args, **kwargs):
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.stop_event = Event()
        self.process = Process(target=self._run, args=(self.stop_event,))

    def _run(self, stop_event):
        while not stop_event.is_set():
            self.callback(*self.args, **self.kwargs)
            sleep(1)

    def start(self):
        self.process.start()

    def stop(self):
        self.stop_event.set()
        self.process.join()
