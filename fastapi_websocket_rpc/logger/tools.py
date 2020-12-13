from timeit import default_timer as timer


class Timer:
    def __init__(self):
        self.start_time = timer()

    def measure_time(self):
        return int((timer() - self.start_time) * 1000)
