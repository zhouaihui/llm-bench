import threading

class User:
    _id_counter = 0
    _id_lock = threading.Lock()

    def __init__(self, prompts):
        self.prompts = prompts
        self.index = 0
        self.id = User._generate_id()

    @classmethod
    def _generate_id(cls):
        with cls._id_lock:
            current_id = cls._id_counter
            cls._id_counter += 1
            return current_id

    @classmethod
    def reset_id_counter(cls):
        with cls._id_lock:
            cls._id_counter = 0

    def has_next(self):
        return self.index < len(self.prompts)

    def next_prompt(self):
        prompt = self.prompts[self.index]
        self.index += 1
        return prompt