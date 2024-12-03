"""
Compiler for a regular grammar.

Example usage::

    # Create and compile grammar.
    p = compile('add \\s+ (?P<var1>[^\\s]+)  \\s+  (?P<var2>[^\\s]+)')

    # Match input string.
    m = p.match('add 23 432')

    # Get variables.
    m.variables().get('var1')  # Returns "23"
    m.variables().get('var2')  # Returns "432"


Partial matches are possible::

    # Create and compile grammar.
    p = compile('''
        # Operators with two arguments.
        ((?P<operator1>[^\\s]+)  \\s+ (?P<var1>[^\\s]+)  \\s+  (?P<var2>[^\\s]+)) |

        # Operators with only one arguments.
        ((?P<operator2>[^\\s]+)  \\s+ (?P<var1>[^\\s]+))
    ''')

    # Match partial input string.
    m = p.match_prefix('add 23')

    # Get variables. (Notice that both operator1 and operator2 contain the
    # value "add".) This is because our input is incomplete, and we don't know
    # yet in which rule of the regex we we'll end up. It could also be that
    # `operator1` and `operator2` have a different autocompleter and we want to
    # call all possible autocompleters that would result in valid input.)
    m.variables().get('var1')  # Returns "23"
    m.variables().get('operator1')  # Returns "add"
    m.variables().get('operator2')  # Returns "add"

"""
from __future__ import annotations
import re
from typing import Callable, Dict, Iterable, Iterator, Pattern
from typing import Match as RegexMatch
from .regex_parser import AnyNode, Lookahead, Node, NodeSequence, Regex, Repeat, Variable, parse_regex, tokenize_regex
__all__ = ['compile']
_INVALID_TRAILING_INPUT = 'invalid_trailing'
EscapeFuncDict = Dict[str, Callable[[str], str]]

class _CompiledGrammar:
    """
    Compiles a grammar. This will take the parse tree of a regular expression
    and compile the grammar.

    :param root_node: :class~`.regex_parser.Node` instance.
    :param escape_funcs: `dict` mapping variable names to escape callables.
    :param unescape_funcs: `dict` mapping variable names to unescape callables.
    """

    def __init__(self, root_node: Node, escape_funcs: EscapeFuncDict | None=None, unescape_funcs: EscapeFuncDict | None=None) -> None:
        self.root_node = root_node
        self.escape_funcs = escape_funcs or {}
        self.unescape_funcs = unescape_funcs or {}
        self._group_names_to_nodes: dict[str, str] = {}
        counter = [0]

        def create_group_func(node: Variable) -> str:
            name = 'n%s' % counter[0]
            self._group_names_to_nodes[name] = node.varname
            counter[0] += 1
            return name
        self._re_pattern = '^%s$' % self._transform(root_node, create_group_func)
        self._re_prefix_patterns = list(self._transform_prefix(root_node, create_group_func))
        flags = re.DOTALL
        self._re = re.compile(self._re_pattern, flags)
        self._re_prefix = [re.compile(t, flags) for t in self._re_prefix_patterns]
        self._re_prefix_with_trailing_input = [re.compile('(?:{})(?P<{}>.*?)$'.format(t.rstrip('$'), _INVALID_TRAILING_INPUT), flags) for t in self._re_prefix_patterns]

    def escape(self, varname: str, value: str) -> str:
        """
        Escape `value` to fit in the place of this variable into the grammar.
        """
        if varname in self.escape_funcs:
            return self.escape_funcs[varname](value)
        return re.escape(value)

    def unescape(self, varname: str, value: str) -> str:
        """
        Unescape `value`.
        """
        if varname in self.unescape_funcs:
            return self.unescape_funcs[varname](value)
        return value

    @classmethod
    def _transform(cls, root_node: Node, create_group_func: Callable[[Variable], str]) -> str:
        """
        Turn a :class:`Node` object into a regular expression.

        :param root_node: The :class:`Node` instance for which we generate the grammar.
        :param create_group_func: A callable which takes a `Node` and returns the next
            free name for this node.
        """
        if isinstance(root_node, Regex):
            return root_node.regex
        elif isinstance(root_node, Variable):
            return f'(?P<{create_group_func(root_node)}>{cls._transform(root_node.childnode, create_group_func)})'
        elif isinstance(root_node, Repeat):
            transformed = cls._transform(root_node.childnode, create_group_func)
            if root_node.max_repeat is None:
                if root_node.min_repeat == 0:
                    return f'({transformed})*'
                elif root_node.min_repeat == 1:
                    return f'({transformed})+'
            return f'({transformed}){{{root_node.min_repeat},{root_node.max_repeat or ""}}}'
        elif isinstance(root_node, AnyNode):
            return '(' + '|'.join(cls._transform(c, create_group_func) for c in root_node.children) + ')'
        elif isinstance(root_node, NodeSequence):
            return ''.join(cls._transform(c, create_group_func) for c in root_node.children)
        else:
            raise ValueError(f'Unknown node: {root_node}')

    @classmethod
    def _transform_prefix(cls, root_node: Node, create_group_func: Callable[[Variable], str]) -> Iterable[str]:
        """
        Yield all the regular expressions matching a prefix of the grammar
        defined by the `Node` instance.

        For each `Variable`, one regex pattern will be generated, with this
        named group at the end. This is required because a regex engine will
        terminate once a match is found. For autocompletion however, we need
        the matches for all possible paths, so that we can provide completions
        for each `Variable`.

        - So, in the case of an `Any` (`A|B|C)', we generate a pattern for each
          clause. This is one for `A`, one for `B` and one for `C`. Unless some
          groups don't contain a `Variable`, then these can be merged together.
        - In the case of a `NodeSequence` (`ABC`), we generate a pattern for
          each prefix that ends with a variable, and one pattern for the whole
          sequence. So, that's one for `A`, one for `AB` and one for `ABC`.

        :param root_node: The :class:`Node` instance for which we generate the grammar.
        :param create_group_func: A callable which takes a `Node` and returns the next
            free name for this node.
        """
        if isinstance(root_node, Regex):
            yield root_node.regex
        elif isinstance(root_node, Variable):
            yield f'(?P<{create_group_func(root_node)}>{cls._transform(root_node.childnode, create_group_func)})'
        elif isinstance(root_node, Repeat):
            transformed = cls._transform(root_node.childnode, create_group_func)
            yield f'({transformed})*'
            if root_node.min_repeat > 0:
                yield f'({transformed})+'
        elif isinstance(root_node, AnyNode):
            for child in root_node.children:
                yield from cls._transform_prefix(child, create_group_func)
        elif isinstance(root_node, NodeSequence):
            current = ''
            for child in root_node.children:
                for prefix in cls._transform_prefix(child, create_group_func):
                    yield current + prefix
                current += cls._transform(child, create_group_func)
            yield current
        else:
            raise ValueError(f'Unknown node: {root_node}')

    def match(self, string: str) -> Match | None:
        """
        Match the string with the grammar.
        Returns a :class:`Match` instance or `None` when the input doesn't match the grammar.

        :param string: The input string.
        """
        m = self._re.match(string)
        if m:
            return Match(string, [(self._re, m)], self._group_names_to_nodes, self.unescape_funcs)
        return None

    def match_prefix(self, string: str) -> Match | None:
        """
        Do a partial match of the string with the grammar. The returned
        :class:`Match` instance can contain multiple representations of the
        match. This will never return `None`. If it doesn't match at all, the "trailing input"
        part will capture all of the input.

        :param string: The input string.
        """
        matches = []
        for re in self._re_prefix_with_trailing_input:
            m = re.match(string)
            if m:
                matches.append((re, m))
        return Match(string, matches, self._group_names_to_nodes, self.unescape_funcs)

class Match:
    """
    :param string: The input string.
    :param re_matches: List of (compiled_re_pattern, re_match) tuples.
    :param group_names_to_nodes: Dictionary mapping all the re group names to the matching Node instances.
    """

    def __init__(self, string: str, re_matches: list[tuple[Pattern[str], RegexMatch[str]]], group_names_to_nodes: dict[str, str], unescape_funcs: dict[str, Callable[[str], str]]):
        self.string = string
        self._re_matches = re_matches
        self._group_names_to_nodes = group_names_to_nodes
        self._unescape_funcs = unescape_funcs

    def _nodes_to_regs(self) -> list[tuple[str, tuple[int, int]]]:
        """
        Return a list of (varname, reg) tuples.
        """
        result = []
        for re, match in self._re_matches:
            for group_name, node_name in self._group_names_to_nodes.items():
                start, end = match.span(group_name)
                if start >= 0:
                    result.append((node_name, (start, end)))
        return result

    def _nodes_to_values(self) -> list[tuple[str, str, tuple[int, int]]]:
        """
        Returns list of (Node, string_value) tuples.
        """
        result = []
        for re, match in self._re_matches:
            for group_name, node_name in self._group_names_to_nodes.items():
                value = match.group(group_name)
                if value is not None:
                    start, end = match.span(group_name)
                    result.append((node_name, value, (start, end)))
        return result

    def variables(self) -> Variables:
        """
        Returns :class:`Variables` instance.
        """
        return Variables(self._nodes_to_values())

    def trailing_input(self) -> MatchVariable | None:
        """
        Get the `MatchVariable` instance, representing trailing input, if there is any.
        "Trailing input" is input at the end that does not match the grammar anymore, but
        when this is removed from the end of the input, the input would be a valid string.
        """
        for re, match in self._re_matches:
            trailing = match.groupdict().get(_INVALID_TRAILING_INPUT)
            if trailing:
                start, end = match.span(_INVALID_TRAILING_INPUT)
                return MatchVariable(_INVALID_TRAILING_INPUT, trailing, (start, end))
        return None

    def end_nodes(self) -> Iterable[MatchVariable]:
        """
        Yields `MatchVariable` instances for all the nodes having their end
        position at the end of the input string.
        """
        input_length = len(self.string)
        for varname, value, (start, end) in self._nodes_to_values():
            if end == input_length:
                yield MatchVariable(varname, value, (start, end))

class Variables:

    def __init__(self, tuples: list[tuple[str, str, tuple[int, int]]]) -> None:
        self._tuples = tuples

    def __repr__(self) -> str:
        return '{}({})'.format(self.__class__.__name__, ', '.join((f'{k}={v!r}' for k, v, _ in self._tuples)))

    def __getitem__(self, key: str) -> str | None:
        return self.get(key)

    def __iter__(self) -> Iterator[MatchVariable]:
        """
        Yield `MatchVariable` instances.
        """
        for varname, value, slice in self._tuples:
            yield MatchVariable(varname, value, slice)

class MatchVariable:
    """
    Represents a match of a variable in the grammar.

    :param varname: (string) Name of the variable.
    :param value: (string) Value of this variable.
    :param slice: (start, stop) tuple, indicating the position of this variable
                  in the input string.
    """

    def __init__(self, varname: str, value: str, slice: tuple[int, int]) -> None:
        self.varname = varname
        self.value = value
        self.slice = slice
        self.start = self.slice[0]
        self.stop = self.slice[1]

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.varname!r}, {self.value!r})'

def compile(expression: str, escape_funcs: EscapeFuncDict | None=None, unescape_funcs: EscapeFuncDict | None=None) -> _CompiledGrammar:
    """
    Compile grammar (given as regex string), returning a `CompiledGrammar`
    instance.
    """
    tokens = tokenize_regex(expression)
    root_node = parse_regex(tokens)
    return _compile_from_parse_tree(root_node, escape_funcs, unescape_funcs)

def _compile_from_parse_tree(root_node: Node, escape_funcs: EscapeFuncDict | None=None, unescape_funcs: EscapeFuncDict | None=None) -> _CompiledGrammar:
    """
    Compile grammar (given as parse tree), returning a `CompiledGrammar`
    instance.
    """
    return _CompiledGrammar(root_node, escape_funcs, unescape_funcs)
