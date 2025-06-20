from typing import get_origin, Union, get_args


def get_field_info(f):
    """Extract information about a dataclass field: type, optional, and default.

    Args:
        f: The field to extract information from.

    Returns: A dict with the field's type, whether it's optional, and its default value.
    """
    field_type = f.type
    optional = False

    # for types like Union[str, None], find the non-None type and set optional to True
    # this is useful for the frontend to know if a field is optional
    # and to show the correct type in the UI
    origin = get_origin(field_type)
    if origin is Union:
        types = get_args(field_type)
        non_none_arg = next((t for t in types if t is not type(None)), None)
        if non_none_arg is not None:
            field_type = non_none_arg
            optional = True

    # type name in a pretty format
    type_name = (
        field_type.__name__ if hasattr(field_type, '__name__') else str(field_type)
    )

    # default is always present
    default = f.default

    # return a schema with the useful info for frontend
    return {'type': type_name.lower(), 'optional': optional, 'default': default}
