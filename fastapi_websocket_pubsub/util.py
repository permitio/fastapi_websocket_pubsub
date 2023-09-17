import pydantic
from packaging import version


# Helper methods for supporting Pydantic v1 and v2
def is_pydantic_pre_v2():
    return version.parse(pydantic.VERSION) < version.parse("2.0.0")


def get_model_serializer():
    if is_pydantic_pre_v2():
        return lambda model: model.json()
    else:
        return lambda model: model.model_dump_json()


def get_model_parser():
    if is_pydantic_pre_v2():
        return lambda model, data: model.parse_obj(data)
    else:
        return lambda model, data: model.model_validate(data)
