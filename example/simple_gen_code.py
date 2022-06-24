from example.python_example_proto_code.example_proto.user import user_pb2
from protobuf_to_pydantic import msg_to_pydantic_model
from protobuf_to_pydantic.gen_code import pydantic_model_to_py_code

print(
    pydantic_model_to_py_code(
        msg_to_pydantic_model(user_pb2.CreateUserRequest),
        msg_to_pydantic_model(user_pb2.CreateUserRequest, parse_msg_desc_method=user_pb2),
    )
)