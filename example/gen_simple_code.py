import importlib
import inspect
import pathlib

from google.protobuf import __version__
from google.protobuf.message import Message

from protobuf_to_pydantic import msg_to_pydantic_model, pydantic_model_to_py_file

target_p: str = "proto" if __version__ > "4.0.0" else "proto_3_20"

module = importlib.import_module(f"example.{target_p}.example.example_proto.demo.demo_pb2")
message_class_list = []
for module_name in dir(module):
    message_class = getattr(module, module_name)
    if not inspect.isclass(message_class):
        continue
    if not issubclass(message_class, Message):
        continue
    message_class_list.append(message_class)

now_path: pathlib.Path = pathlib.Path(__file__).absolute()


def gen_code() -> None:
    pydantic_model_to_py_file(
        str(now_path.parent.joinpath(target_p, "demo_gen_code.py")),
        *[msg_to_pydantic_model(model) for model in message_class_list],
    )


if __name__ == "__main__":
    gen_code()
