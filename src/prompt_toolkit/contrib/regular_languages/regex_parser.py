"""
Parser for parsing a regular expression.
Take a string representing a regular expression and return the root node of its
parse tree.

usage::

    root_node = parse_regex('(hello|world)')

Remarks:
- The regex parser processes multiline, it ignores all whitespace and supports
  multiple named groups with the same name and #-style comments.

Limitations:
- Lookahead is not supported.
"""
from __future__ import annotations
import re
__all__ = ['Repeat', 'Variable', 'Regex', 'Lookahead', 'tokenize_regex', 'parse_regex']

class Node:
    """
    Base class for all the grammar nodes.
    (You don't initialize this one.)
    """

    def __add__(self, other_node: Node) -> NodeSequence:
        return NodeSequence([self, other_node])

    def __or__(self, other_node: Node) -> AnyNode:
        return AnyNode([self, other_node])

class AnyNode(Node):
    """
    Union operation (OR operation) between several grammars. You don't
    initialize this yourself, but it's a result of a "Grammar1 | Grammar2"
    operation.
    """

    def __init__(self, children: list[Node]) -> None:
        self.children = children

    def __or__(self, other_node: Node) -> AnyNode:
        return AnyNode(self.children + [other_node])

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.children!r})'

class NodeSequence(Node):
    """
    Concatenation operation of several grammars. You don't initialize this
    yourself, but it's a result of a "Grammar1 + Grammar2" operation.
    """

    def __init__(self, children: list[Node]) -> None:
        self.children = children

    def __add__(self, other_node: Node) -> NodeSequence:
        return NodeSequence(self.children + [other_node])

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.children!r})'

class Regex(Node):
    """
    Regular expression.
    """

    def __init__(self, regex: str) -> None:
        re.compile(regex)
        self.regex = regex

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(/{self.regex}/)'

class Lookahead(Node):
    """
    Lookahead expression.
    """

    def __init__(self, childnode: Node, negative: bool=False) -> None:
        self.childnode = childnode
        self.negative = negative

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.childnode!r})'

class Variable(Node):
    """
    Mark a variable in the regular grammar. This will be translated into a
    named group. Each variable can have his own completer, validator, etc..

    :param childnode: The grammar which is wrapped inside this variable.
    :param varname: String.
    """

    def __init__(self, childnode: Node, varname: str='') -> None:
        self.childnode = childnode
        self.varname = varname

    def __repr__(self) -> str:
        return '{}(childnode={!r}, varname={!r})'.format(self.__class__.__name__, self.childnode, self.varname)

class Repeat(Node):

    def __init__(self, childnode: Node, min_repeat: int=0, max_repeat: int | None=None, greedy: bool=True) -> None:
        self.childnode = childnode
        self.min_repeat = min_repeat
        self.max_repeat = max_repeat
        self.greedy = greedy

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(childnode={self.childnode!r})'

def tokenize_regex(input: str) -> list[str]:
    """
    Takes a string, representing a regular expression as input, and tokenizes
    it.

    :param input: string, representing a regular expression.
    :returns: List of tokens.
    """
    tokens = []
    i = 0
    input = re.sub(r'\s+', '', input)  # Remove all whitespace
    
    while i < len(input):
        if input[i] in '()|?*+.[]^$':
            tokens.append(input[i])
            i += 1
        elif input[i] == '\\':
            if i + 1 < len(input):
                tokens.append(input[i:i+2])
                i += 2
            else:
                tokens.append(input[i])
                i += 1
        elif input[i] == '{':
            end = input.find('}', i)
            if end != -1:
                tokens.append(input[i:end+1])
                i = end + 1
            else:
                tokens.append(input[i])
                i += 1
        else:
            tokens.append(input[i])
            i += 1
    
    return tokens

def parse_regex(regex_tokens: list[str]) -> Node:
    """
    Takes a list of tokens from the tokenizer, and returns a parse tree.
    """
    def parse_sequence() -> Node:
        sequence = []
        while tokens and tokens[0] not in ')|':
            sequence.append(parse_atom())
        return NodeSequence(sequence) if len(sequence) > 1 else sequence[0]

    def parse_atom() -> Node:
        if not tokens:
            raise ValueError("Unexpected end of regex")
        
        token = tokens.pop(0)
        
        if token == '(':
            node = parse_sequence()
            if not tokens or tokens.pop(0) != ')':
                raise ValueError("Unmatched parenthesis")
        elif token == '[' or token.startswith('\\'):
            node = Regex(token)
        else:
            node = Regex(re.escape(token))
        
        while tokens and tokens[0] in '*+?{':
            quantifier = tokens.pop(0)
            if quantifier == '{':
                end = tokens.index('}')
                quantifier += ''.join(tokens[:end+1])
                tokens = tokens[end+1:]
            min_repeat, max_repeat = 0, None
            greedy = True
            
            if quantifier == '*':
                max_repeat = None
            elif quantifier == '+':
                min_repeat = 1
                max_repeat = None
            elif quantifier == '?':
                max_repeat = 1
            elif quantifier.startswith('{'):
                parts = quantifier[1:-1].split(',')
                min_repeat = int(parts[0])
                max_repeat = int(parts[1]) if len(parts) > 1 and parts[1] else None
            
            if tokens and tokens[0] == '?':
                greedy = False
                tokens.pop(0)
            
            node = Repeat(node, min_repeat, max_repeat, greedy)
        
        return node

    tokens = regex_tokens.copy()
    result = parse_sequence()
    
    while tokens and tokens[0] == '|':
        tokens.pop(0)
        result = result | parse_sequence()
    
    if tokens:
        raise ValueError(f"Unexpected tokens: {''.join(tokens)}")
    
    return result
