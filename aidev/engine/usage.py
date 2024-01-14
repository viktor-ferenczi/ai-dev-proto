import json

from pydantic import BaseModel


class Usage(BaseModel):
    generations: int = 0
    completions: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def save(self, path: str):
        data = self.model_dump_json(indent=2)
        with open(path, 'wb') as f:
            json.dump(data, f)

    def load(self, path: str):
        with open(path, 'rb') as f:
            data = json.load(f)
        self.__dict__.update(data)
