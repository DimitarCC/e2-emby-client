from threading import Thread, Event


class StoppableThread(Thread):
    def __init__(self, id, target, args=(), kwargs=None):
        self.id = id
        self.name = "EmbyListThread-" + str(id)
        super().__init__(name=self.name)
        self._stop_event = Event()
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

    def __eq__(self, other):
        if isinstance(other, StoppableThread):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.name)
