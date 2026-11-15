# The smallest workspace there is: one agent, in five lines.
#
#   pact check examples/language/hello/hello.pact
workspace "Hello"

agent greeter
  description: Says hello.
  instructions: Greet whoever writes to you, in one friendly sentence.
