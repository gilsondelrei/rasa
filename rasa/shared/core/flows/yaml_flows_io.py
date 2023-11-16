import textwrap
from pathlib import Path
from typing import Any, Dict, List, Text, Union

import jsonschema

import rasa.shared
import rasa.shared.data
import rasa.shared.utils.io
import rasa.shared.utils.validation
from rasa.shared.exceptions import RasaException, YamlException

from rasa.shared.core.flows.flow import Flow
from rasa.shared.core.flows.flows_list import FlowsList

FLOWS_SCHEMA_FILE = "shared/core/flows/flows_yaml_schema.json"
KEY_FLOWS = "flows"


class YAMLFlowsReader:
    """Class that reads flows information in YAML format."""

    @classmethod
    def read_from_file(
        cls, filename: Union[Text, Path], skip_validation: bool = False
    ) -> FlowsList:
        """Read flows from file.

        Args:
            filename: Path to the flows file.
            skip_validation: `True` if the file was already validated
                e.g. when it was stored in the database.

        Returns:
            `Flow`s read from `filename`.
        """
        try:
            return cls.read_from_string(
                rasa.shared.utils.io.read_file(
                    filename, rasa.shared.utils.io.DEFAULT_ENCODING
                ),
                skip_validation,
            )
        except YamlException as e:
            e.filename = str(filename)
            raise e
        except RasaException as e:
            raise YamlException(filename) from e

    @staticmethod
    def humanize_flow_error(error: jsonschema.ValidationError) -> str:
        """Create a human understandable error message from a validation error."""

        def errornuous_property(path: List[Any]) -> str:
            if not path:
                return "schema"
            if isinstance(path[-1], int):
                # the path is pointing towards an element in a list, so
                # we use the name of the list if possible
                return path[-2] if len(path) > 1 else "list"
            return str(path[-1])

        def schema_name(schema: Dict[str, Any]) -> str:
            return schema.get("schema_name", schema.get("type"))

        def schema_names(schemas: List[Dict[str, Any]]) -> List[str]:
            names = []
            for schema in schemas:
                if name := schema_name(schema):
                    names.append(name)
            return names

        def expected_schema(error: jsonschema.ValidationError, schema_type: str) -> str:
            expected_schemas = error.schema.get(schema_type, [])
            expected = schema_names(expected_schemas)
            if expected:
                return " or ".join(sorted(expected))
            else:
                return str(error.schema)

        def format_oneof_error(error: jsonschema.ValidationError) -> str:
            return (
                f"Not a valid '{errornuous_property(error.absolute_path)}' definition. "
                f"Expected {expected_schema(error, 'oneOf')}."
            )

        def format_anyof_error(error: jsonschema.ValidationError) -> str:
            return (
                f"Not a valid '{errornuous_property(error.absolute_path)}' definition. "
                f"Expected {expected_schema(error, 'anyOf')}."
            )

        def format_type_error(error: jsonschema.ValidationError) -> str:
            expected_value = schema_name(error.schema)
            if isinstance(error.instance, dict):
                instance = "a dictionary"
            elif isinstance(error.instance, list):
                instance = "a list"
            else:
                instance = f"`{error.instance}`"
            return f"Found {instance} but expected a {expected_value}."

        if error.validator == "oneOf":
            return format_oneof_error(error)

        if error.validator == "anyOf":
            return format_anyof_error(error)

        if error.validator == "type":
            return format_type_error(error)

        return (
            f"The flow at {error.json_path} is not valid. "
            f"Please double check your flow definition."
        )

    @classmethod
    def read_from_string(cls, string: Text, skip_validation: bool = False) -> FlowsList:
        """Read flows from a string.

        Args:
            string: Unprocessed YAML file content.
            skip_validation: `True` if the string was already validated
                e.g. when it was stored in the database.

        Returns:
            `Flow`s read from `string`.
        """
        if not skip_validation:
            rasa.shared.utils.validation.validate_yaml_with_jsonschema(
                string, FLOWS_SCHEMA_FILE, humanize_error=cls.humanize_flow_error
            )

        yaml_content = rasa.shared.utils.io.read_yaml(string)

        flows = FlowsList.from_json(yaml_content.get(KEY_FLOWS, {}))
        if not skip_validation:
            flows.validate()
        return flows


class YamlFlowsWriter:
    """Class that writes flows information in YAML format."""

    @staticmethod
    def dumps(flows: List[Flow]) -> Text:
        """Dump `Flow`s to YAML.

        Args:
            flows: The `Flow`s to dump.

        Returns:
            The dumped YAML.
        """
        dump = {}
        for flow in flows:
            dumped_flow = flow.as_json()
            del dumped_flow["id"]
            dump[flow.id] = dumped_flow
        return rasa.shared.utils.io.dump_obj_as_yaml_to_string({KEY_FLOWS: dump})

    @staticmethod
    def dump(flows: List[Flow], filename: Union[Text, Path]) -> None:
        """Dump `Flow`s to YAML file.

        Args:
            flows: The `Flow`s to dump.
            filename: The path to the file to write to.
        """
        rasa.shared.utils.io.write_text_file(YamlFlowsWriter.dumps(flows), filename)


def flows_from_str(yaml_str: str) -> FlowsList:
    """Reads flows from a YAML string."""
    return YAMLFlowsReader.read_from_string(textwrap.dedent(yaml_str))


def is_flows_file(file_path: Union[Text, Path]) -> bool:
    """Check if file contains Flow training data.

    Args:
        file_path: Path of the file to check.

    Returns:
        `True` in case the file is a flows YAML training data file,
        `False` otherwise.

    Raises:
        YamlException: if the file seems to be a YAML file (extension) but
            can not be read / parsed.
    """
    return rasa.shared.data.is_likely_yaml_file(
        file_path
    ) and rasa.shared.utils.io.is_key_in_yaml(file_path, KEY_FLOWS)
