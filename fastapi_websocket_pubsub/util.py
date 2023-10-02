import pydantic
from packaging import version


# Helper methods for supporting Pydantic v1 and v2
def is_pydantic_pre_v2():
    return version.parse(pydantic.VERSION) < version.parse("2.0.0")


def pydantic_serialize(model, **kwargs):
    if is_pydantic_pre_v2():
        return model.json(**kwargs)
    else:
        return model.model_dump_json(**kwargs)


def pydantic_to_dict(model, **kwargs):
    if is_pydantic_pre_v2():
        return model.dict(**kwargs)
    else:
        return model.model_dump(**kwargs)
