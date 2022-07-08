import inspect
import pathlib
import sys
import time
from collections import deque
from enum import IntEnum
from typing import _GenericAlias  # type: ignore
from typing import Any, Deque, Optional, Set, Tuple, Type

from pydantic import BaseModel


def _parse_base_model_class(value_type: Any, import_set: Set[str], content_deque: Deque, module_path: str) -> None:
    def _parse_to_set(real_type: Any) -> None:
        if real_type.__module__ == "builtins":
            return
        if isinstance(real_type, _GenericAlias):
            import_set.add("import typing")
            for real_type in value_type.__args__:
                _parse_to_set(real_type)
            return
        if inspect.isclass(real_type) and issubclass(real_type, BaseModel):
            _import_set, _content_deque = _pydantic_model_to_py_code(real_type, module_path)
            if _import_set:
                import_set.update(_import_set)
            if _content_deque:
                content_deque.extend(_content_deque)
        elif hasattr(real_type, "__module__") and hasattr(real_type, "__name__"):
            import_set.add(f"from {real_type.__module__} import {real_type.__name__}")

    _parse_to_set(value_type)


def _pydantic_model_to_py_code(model: Type[BaseModel], module_path: str = "") -> Tuple[Set[str], Deque]:
    import_set: Set[str] = {"from pydantic import BaseModel"}
    content_deque: Deque = deque()
    class_str: str = f"class {model.__name__}(BaseModel):\n"
    for key, value in model.__fields__.items():
        value_type = value.outer_type_
        value_type_name: str = getattr(value_type, "__name__", None)
        if value.outer_type_.__module__ != "builtins":
            if inspect.isclass(value.type_) and issubclass(value.type_, IntEnum):
                import_set.add("from enum import IntEnum")
                depend_set_str = f"class {value.type_.__name__}(IntEnum):\n"
                for enum_name, enum_value in value.type_.__members__.items():
                    depend_set_str += " " * 4 + f"{enum_name} = {enum_value.value}\n"
                content_deque.append(depend_set_str)
            else:
                # It is not necessary to consider other types since
                # it is converted from the message object generated by protobuf
                value_type = model.__annotations__[key]
                _parse_base_model_class(value_type, import_set, content_deque, module_path)
            if isinstance(value_type, _GenericAlias):
                value_type_name = f"typing.{value_type._name}[{', '.join([i.__name__ for i in value_type.__args__])}]"
            else:
                value_type_name = getattr(value_type, "__name__", None)

        import_set.add(f"from {value.field_info.__module__} import {value.field_info.__class__.__name__}")
        # Introduce the corresponding class for FieldInfo's properties
        field_list = []
        for k, v in value.field_info.__repr_args__():
            if k == "default" and str(v) == "PydanticUndefined":
                continue
            if k == "extra" and not v:
                continue
            value_module = inspect.getmodule(v)

            value_name: str = repr(v)
            if value_module and value_module.__name__ == "builtins" or inspect.isfunction(v):
                value_name = v.__name__
            value_name = value_name.replace("'", '"')
            field_list.append(f"{k}={value_name}")

            if inspect.isclass(v):
                class_name: str = v.__name__
            elif not inspect.isfunction(v):
                class_name = v.__class__.__name__
            else:
                class_name = v.__name__

            if not value_module:
                continue
            if value_module.__name__ == "builtins":
                continue
            elif value_module.__name__ == "__main__":
                start_path: str = sys.path[0]
                if module_path:
                    module_name = module_path.split("/")[-1] + value_module.__file__.replace(module_path, "")
                else:
                    # Find the name of the module for the variable that starts the code file
                    if not value_module.__file__.startswith(start_path):
                        # Compatible scripts are run directly in the submodule
                        module_name = f"{start_path.split('/')[-1]}.{value_module.__file__.split('/')[-1]}"
                    else:
                        module_name = start_path.split("/")[-1] + value_module.__file__.replace(start_path, "")
                module_name = module_name.replace("/", ".").replace(".py", "")
                class_name = value_name
            else:
                module_name = value_module.__name__

            import_set.add(f"from {module_name} import {class_name}")

        field_str: str = f"{value.field_info.__class__.__name__}({', '.join(field_list)})"
        class_str = class_str + " " * 4 + f"{key}: {value_type_name} = {field_str}\n"

    validator_str: str = ""
    for key, value in model.__fields__.items():
        if not value.class_validators:
            continue
        for class_validator_key, class_validator_value in value.class_validators.items():
            if class_validator_value.func.__module__ != "protobuf_to_pydantic.get_desc.from_pgv":
                # TODO Here currently only consider the support for pgv, the follow-up to fill in
                continue
            content_deque.append(inspect.getsource(class_validator_value.func))
            import_set.add("from pydantic import validator")
            import_set.add("from typing import Any")
            validator_str += (
                f"{' ' * 4}"
                f"{class_validator_key}_{key} = validator("
                f"'{key}', allow_reuse=True)({class_validator_value.func.__name__})\n"
            )
    if validator_str:
        class_str += f"\n{validator_str}"
    content_deque.append(class_str)
    return import_set, content_deque


def pydantic_model_to_py_code(
    *model: Type[BaseModel],
    customer_import_set: Optional[Set[str]] = None,
    customer_deque: Optional[Deque] = None,
    module_path: str = "",
    enable_autoflake: bool = True,
    enable_isort: bool = True,
    enable_yapf: bool = True,
) -> str:
    """
    BaseModel objects into corresponding Python code
    (only protobuf-generated pydantic.BaseModel objects are supported, not overly complex pydantic.BaseModel)
    """
    import_set: Set[str] = customer_import_set or set()
    content_deque: Deque = customer_deque or deque()
    if module_path:
        module_path_obj: pathlib.Path = pathlib.Path(module_path).absolute()
        if not module_path_obj.is_dir():
            raise TypeError(f"{module_path} must dir")
        cnt: int = 0
        while True:
            if not module_path_obj.name == "..":
                break
            module_path_obj = module_path_obj.parent
            cnt += 1
        for _ in range(cnt):
            module_path_obj = module_path_obj.parent
        module_path = str(module_path_obj.absolute())

    for _model in model:
        _import_set, _content_deque = _pydantic_model_to_py_code(_model, module_path)
        if _import_set:
            import_set.update(_import_set)
        if _content_deque:
            content_deque.extend(_content_deque)

    content_str: str = (
        "# This is an automatically generated file, please do not change\n"
        "# gen by protobuf_to_pydantic(https://github.com/so1n/protobuf_to_pydantic)\n"
        f"# gen timestamp:{int(time.time())}\n\n"
    )

    content_str += "\n".join(sorted(import_set))
    if content_deque:
        _content_set: Set[str] = set()
        content_str += "\n\n"
        while content_deque:
            content = content_deque.popleft()
            if content in _content_set:
                continue
            _content_set.add(content)
            content_str += f"\n\n{content}"

    if enable_isort:
        try:
            import isort
        except ImportError:
            pass
        else:
            content_str = isort.code(content_str)

    if enable_autoflake:
        try:
            import autoflake
        except ImportError:
            pass
        else:
            content_str = autoflake.fix_code(content_str)

    if enable_yapf:
        try:
            from yapf.yapflib.yapf_api import FormatCode
        except ImportError:
            pass
        else:
            content_str, _ = FormatCode(content_str)

    # TODO Waiting for black development API
    # https://github.com/psf/black/issues/779
    return content_str


def pydantic_model_to_py_file(
    filename: str,
    *model: Type[BaseModel],
    customer_import_set: Optional[Set[str]] = None,
    customer_deque: Optional[Deque] = None,
    open_mode: str = "w",
    module_path: str = "",
) -> None:
    with open(filename, mode=open_mode) as f:
        f.write(
            pydantic_model_to_py_code(
                *model, customer_import_set=customer_import_set, customer_deque=customer_deque, module_path=module_path
            )
        )
