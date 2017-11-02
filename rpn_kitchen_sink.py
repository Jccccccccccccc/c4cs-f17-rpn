#!/usr/bin/env python3

# vim: tabstop=4 shiftwidth=4 softtabstop=4 expandtab
#
# This is a "modeline", which tells vim how to handle tabs an spaces (many other
# editors will also respect vim modelines). By default, vim ignores modelines,
# however, if you add "set modeline" to your .vimrc it will pay attention to
# this line.


# The logging library is standard way to emit log messages in Python. Most
# modern languages have an official logging mechanism and it's a good idea to
# use it. It will let users of your library turn logging of your code on and off
# as they please.
import logging
log = logging.getLogger(__name__)


# There are multiple python implementations. Sometimes, they have slightly
# different features. The default "python" installed on most systems cPython, an
# implementation written in C.
#
# Another implementation is PyPy, a Python interpreter written in Python. If the
# user happens to run this program with PyPy instead of cPython, we can unlock
# an advanced feature.
#
# The idea is that we can import arbitrary functions from the "math" library,
# such as math.pow to take exponents and math.sin for trigonometry.  However,
# pow takes 2 arguments, but sin only takes 1. For functions implemented in
# Python, Python can inspect the function to see how many arguments it takes.
# Python can't inspect functions written in C, however, and in cPython, the math
# library is implemented in C. Most math functions take 2 arguments, so for
# cPython, just do a lazy best-effort approach.
import platform
if platform.python_implementation() == 'PyPy':
    # PyPy only supports Python2.7, which changes input() behavior
    input = raw_input
    import inspect
    def get_math_arg_count(fn):
        return len(inspect.getargspec(fn).args)
else:
    def get_math_arg_count(fn):
        # Sadly, there's no way to introspect built-in functions in cPython, so
        # manually throw in a few of the common ones and then hope for the best
        if fn.__name__ in ('cos', 'sin', 'tan', 'exp', 'sqrt'):
            return 1
        return 2



# "readline" is the name of library that handles input in a normal terminal.
# There are readline implementations for most programming languages, which will
# make your program automatically behave like the terminal does (up/down
# history, Ctrl-R to search history, Ctrl-A to beginning of line, etc)
import readline

# We can actually go a step further and add tab-completion. Let's support tab
# completion for all of the functions provided by math. We'll need the regular
# expressions library (re)
import re
def completion_function(text, state):
    completions = [c for c in dir(math) if re.search('^'+text+'[^_].*', c)]
    try:
        return completions[state]
    except IndexError:
        return None

readline.parse_and_bind("tab: complete")
readline.set_completer(completion_function)


# It would be nice if our calculator can identify something like:
#
# $ cat commands | ./rpn       or      $ ./rpn < commands
#
# And not print the "rpn calc>" prompt in the non-interactive case
#
# I'd never done that before, so I googled, python detect pipe input
# which led me to
# http://stackoverflow.com/questions/13442574/how-do-i-determine-if-sys-stdin-is-redirected-from-a-file-vs-piped-from-another
#
# Notice we check this _before_ argument parsing so the default echo
# and session recording behavoir changes
import os, stat

mode = os.fstat(0).st_mode
interactive_session = not (stat.S_ISFIFO(mode) or stat.S_ISREG(mode))
if interactive_session:
    prompt = 'rpn calc> '
else:
    prompt = ''


# The argparse library makes generating and using command line arguments easy
# It also builds in a "-h" for help for free. Try it out!
import argparse
parser = argparse.ArgumentParser(description="A simple RPN Calculator")
parser.add_argument('-F', '--disable-floats', action='store_true',
        help="Act as an integer-only calculator")
parser.add_argument('-i', '--show-intermediates', action='store_true',
        help="Show intermediate steps during calculation")
parser.add_argument('-e', '--echo', action='store_true',
        default=False if interactive_session else True,
        help="Echo input expressions before running")
parser.add_argument('-r', '--record-file',
        default='/tmp/rpn.log' if interactive_session else '/dev/null',
        help="Record the expression into this record file")
args = parser.parse_args()


# Finally a few other packages that our program uses
import math
import operator


class Calculator:
    '''A Reverse Polish Notation Calculator'''

    def __init__(self):
        self.last = 0
        self.coerce_number = float

        self.OPERATORS = {
            '+': operator.add,
            '-': operator.sub,
            '*': operator.mul,
            '/': operator.truediv,
            }


    def lookup(self, operand):
        '''Convert operand to (executable, arg_count)

        This method that takes an operand ('1', '+', 'pow') as a string a
        returns a function that can be called. The return value of the returned
        function is should be appended to the execution stack. The second value
        returned is the number of arguments the function requires
        '''
        log.debug(operand)
        if operand == '.':
            return (lambda: self.last, 0)

        try:
            operand = self.coerce_number(operand)
            return (lambda: operand, 0)
        except ValueError:
            pass

        try:
            operand = self.OPERATORS[operand]
            return (lambda *args: operand(*args), 2)
        except KeyError:
            pass

        try:
            operand = getattr(math, operand)
            return (lambda *args: operand(*args), get_math_arg_count(operand))
        except AttributeError:
            pass

        raise RuntimeError("Invalid operand: {}".format(operand))


    def calculate(self, expression):
        stack = []
        for fn,count in map(self.lookup, expression.split()):
            stack.append(fn(*(stack.pop() for x in range(count))))
            if args.show_intermediates and count:
                print("[intermediate]: {}".format(stack[-1]))
            log.debug(stack)
        if len(stack) != 1:
            raise RuntimeError("Malformed expression")
        self.last = stack.pop()
        return self.last


class IntegerCalculator(Calculator):
    '''A Reverse Polish Notation Calculator that uses integer math'''
    def __init__(self):
        super().__init__()
        self.OPERATORS['/'] = operator.floordiv
        self.coerce_number = int

    def coerce_number(self, operand):
        return int(operand)


def main():
    calculator = IntegerCalculator() if args.disable_floats else Calculator()

    # Open for in append mode (can also 'r'ead or 'w'rite)
    record = open(args.record_file, 'a')

    while True:
        try:
            to_calculate = input(prompt)

            # Treat bland lines or lines starting with '#' as comments
            if len(to_calculate) == 0 or to_calculate[0] == '#':
                continue

            if args.echo:
                print(to_calculate)

            # 'q'uit
            if to_calculate[0] == 'q':
                break

            answer = calculator.calculate(to_calculate)
            print(answer)

            # By waiting until here to write to the record, we only record
            # executions that were successful
            record.write(to_calculate + '\n')
            record.write('# ' + str(answer) + '\n')

        except RuntimeError as e:
            print("Error:", e)

        # Let the user press Ctrl-d to quit
        except EOFError:
            break

# This lets your program act as both a _script_ and a _module_
if __name__ == '__main__':
    main()

