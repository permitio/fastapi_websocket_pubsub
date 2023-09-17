import pydantic
from packaging import version


# Helper methods for supporting Pydantic v1 and v2
def is_pydantic_pre_v2():
    return version.parse(pydantic.VERSION) < version.parse("2.0.0")


def get_model_serializer():
    if is_pydantic_pre_v2():
        return lambda model, **kwargs: model.json(**kwargs)
    else:
        return lambda model, **kwargs: model.model_dump_json(**kwargs)


def get_model_dict():
    if is_pydantic_pre_v2():
        return lambda model, **kwargs: model.dict(**kwargs)
    else:
        return lambda model, **kwargs: model.model_dump(**kwargs)
