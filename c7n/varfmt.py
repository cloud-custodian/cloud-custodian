from string import Formatter
from c7n.utils import DeferredFormatString


class VarFormat(Formatter):
    """Behaves exactly like the stdlib formatter, with one additional behavior.

    when a string has no format_spec and only contains a single expression,
    retain the type of the source object.

    inspired by https://pypyr.io/docs/substitutions/format-string/
    """

    def _vformat(
        self, format_string, args, kwargs, used_args, recursion_depth, auto_arg_index=0
    ):
        # This is mostly verbatim from stdlib format.Formatter._vformat
        # https://github.com/python/cpython/blob/main/Lib/string.py
        #
        # we have to copy alot of std logic to override the str cast

        if recursion_depth < 0:
            raise ValueError('Max string recursion exceeded')
        result = []
        for literal_text, field_name, format_spec, conversion in self.parse(
            format_string
        ):

            # output the literal text
            if literal_text:
                result.append((literal_text, True, None))

            # if there's a field, output it
            if field_name is not None:
                # this is some markup, find the object and do
                #  the formatting

                # handle arg indexing when empty field_names are given.
                if field_name == '':
                    if auto_arg_index is False:
                        raise ValueError(
                            'cannot switch from manual field '
                            'specification to automatic field '
                            'numbering'
                        )
                    field_name = str(auto_arg_index)
                    auto_arg_index += 1
                elif field_name.isdigit():
                    if auto_arg_index:
                        raise ValueError(
                            'cannot switch from manual field '
                            'specification to automatic field '
                            'numbering'
                        )
                    # disable auto arg incrementing, if it gets
                    # used later on, then an exception will be raised
                    auto_arg_index = False

                # given the field_name, find the object it references
                #  and the argument it came from
                obj, arg_used = self.get_field(field_name, args, kwargs)
                used_args.add(arg_used)

                # do any conversion on the resulting object
                obj = self.convert_field(obj, conversion)

                # expand the format spec, if needed
                format_spec, auto_arg_index = self._vformat(
                    format_spec,
                    args,
                    kwargs,
                    used_args,
                    recursion_depth - 1,
                    auto_arg_index=auto_arg_index,
                )

                # defer format
                result.append((obj, False, format_spec))

        # if input is a single expression (ie. '{expr}' don't cast
        # source to string.
        if len(result) == 1:
            obj, is_literal, format_spec = result[0]
            if is_literal:
                return obj, auto_arg_index
            if format_spec or isinstance(obj, DeferredFormatString):
                return self.format_field(obj, format_spec), auto_arg_index
            else:
                return obj, auto_arg_index
        else:
            return (
                ''.join(
                    [
                        obj if is_literal else self.format_field(obj, format_spec)
                        for obj, is_literal, format_spec in result
                    ]
                ),
                auto_arg_index,
            )
