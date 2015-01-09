# Based on one of the angular DI examples

import time
from collections import namedtuple

from jugular import Inject, Provide, Injector

def has(*args):
    # I got tired of writing __init__s of "self.x = x"
    has.i = getattr(has, 'i', -1)+1
    return namedtuple("Base{}".format(has.i), args)

class Electricity(object):
    pass

@Inject(Electricity)
class Heater(has("electricity")):
    def on(self):
        print("Turning on the coffee heater...")

    def off(self):
        print("Turning off the coffee heater...")

@Inject(Electricity)
class Grinder(has("electricity")):
    def grind(self):
        print("Griding the coffee...")

@Inject(Heater, Electricity, time)
class Pump(has("heater", "electricity", "time")):
  def pump(self):
    print('Pumping the water at time {}...'.format(self.time.time()))

@Inject(Grinder, Pump, Heater, time)
class CoffeeMaker(has("grinder", "pump", "heater", "time")):
  def brew(self):
    print('Brewing a coffee at {}...'.format(self.time.time()))
    self.grinder.grind()
    self.heater.on()
    self.pump.pump()
    self.heater.off()
    print('A coffee is ready at {}.'.format(self.time.time()))


@Provide(Heater)
class MockHeater(object):
  def on(self):
    print('Turning on the MOCK heater...')

  def off(self):
    pass

@Provide(time)
def PlainTime():
    return time

@Provide(time)
class Clock(object):
    def __init__(self):
        self.t=0

    def time(self):
        self.t += 1
        return self.t

print("Brewing coffee with plain time.")
i = Injector([PlainTime])
maker = i.get(CoffeeMaker)
maker.brew()

# Equivalent to:
# e = Electricity()
# h = Heater(e)
# g = Grinder(e)
# t = PlainTime()
# p = Pump(h, e, t)
# maker = CoffeeMaker(g, p, h, t)
# maker.brew()
print('='*80)
print("Brewing coffee with mock heater and auto-advancing integer clock.")
i2 = Injector([MockHeater, Clock])
maker2 = i2.get(CoffeeMaker)
maker2.brew()

print('='*80)
print("Brewing again with the same auto-advancing clock.")
maker3 = i2.get(CoffeeMaker)
maker3.brew()

# Equivalent to:
# e = Electricity()
# h = MockHeater()
# g = Grinder(e)
# t = Clock()
# p = Pump(h, e, t)
# maker2 = CoffeeMaker(g, p, h, t)
# maker2.brew()
# maker3 = maker2.brew()
# maker3.brew()

# Note that if a target is being built by a parent, then so will its
# injections:

i = Injector([PlainTime])
i2 = i.createChild([MockHeater, Clock])
maker = i2.get(CoffeeMaker)
assert maker.pump.time == i.get(time)
assert maker.pump.time != i2.get(time)

# This also means that it's possible to screw up your injections by overriding
# a lower injection but not thing things above it:

i = Injector([PlainTime])
i2 = i.createChild([CoffeeMaker, Clock])

# Now if we ask for a CoffeeMaker, i2 will build it using its `time` provider
# (Clock). But it also needs to inject a Pump, which it doesn't override, so
# it'll ask i for the Pump and i will construct a Pump using its own `time`
# provider (PlainTime).

# If you do all the building at once, the injector will detect this:
try:
    maker = i2.get(CoffeeMaker)
except Exception as e:
    # Not checking the whole string because it ends with the system path to
    # the time module.
    assert e.args[0].startswith("Cyclic or duplicate dependency: <module 'time'")
# If we build it in pieces, though, it won't detect it:
# Ensure that i already has a Pump (with PlainTime)
i.get(Pump)
# Build the CoffeeMaker. i2 will get the Pump from i without ever knowing that
# i used a different `time` to build it
maker = i2.get(CoffeeMaker)
assert maker.time is i2.get(time)
assert maker.pump.time is i.get(time)
assert maker.pump.time is not maker.time

