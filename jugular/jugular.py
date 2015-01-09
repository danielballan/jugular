from collections import namedtuple

Injection = namedtuple("Injection", ("token"))

def Inject(*args):
    def wrap(token):
        inj = getattr(token, '_injections', [])
        for arg in args:
            if not isinstance(arg, Injection):
                arg = Injection(arg)
            inj.append(arg)
        token._injections = inj
        return token
    return wrap

def Provide(interface):
    def wrap(token):
        # Use a list instead of a raw value in case the interface token is a
        # function or some other thing that implements the descriptor protocol
        token._provides = [interface]
        return token
    return wrap

def NoDefault(token):
    token._nodefault=True
    return token

class Scope(object):
    '''Scope is a marker to indicate when a dependency needs to be rebuilt.

    You never actually instantiate a scope (it'll complain if you try).
    Instead, you just create subclasses and use them directly as decorators.

    >>> class MyScope(Scope): pass
    >>> @MyScope
    ... def some_fn(): pass
    >>> some_fn._scopes
    [<class 'jugular.MyScope'>]

    The rule for Providers is that if a Provider contains scope S, and an
    injector is marked as requiring new items at scope T, and S is a subclass
    of T, then the injector will create its own instance from the provider
    even if a parent has one already.
    '''

    def __new__(cls, token=None):
        if token is None:
            raise Exception("Never instantiate Scope.")
        scopes = getattr(token, '_scopes', [])
        scopes.append(cls)
        token._scopes = scopes
        return token

class TransientScope(Scope): pass

def get_token(module):
    if hasattr(module, '_provides'):
        return module._provides[0]
    return module

def get_scopes(module):
    return getattr(module, '_scopes', [])

def get_params(module):
    # TODO scan python3 annotations as well
    # Or provide decorator that scans p3 annotations and adds to _injections
    return getattr(module, '_injections', [])

class Provider(object):
    # Subclasses should set .params
    def clearedAtScope(self, scope):
        for my_scope in self.scopes:
            if issubclass(my_scope, scope):
                return True
        return False

    def create(self, *args, **kwargs):
        raise NotImplementedError()

class FactoryProvider(Provider):
    def __init__(self, factory, params, scopes):
        self._factory = factory
        self.params = params
        self.scopes = scopes
        if hasattr(factory, 'release'):
            self.release = factory.release

    def clearedAtScope(self, scope):
        for my_scope in self.scopes:
            if issubclass(my_scope, scope):
                return True
        return False

    def create(self, *args, **kwargs):
        return self._factory(*args, **kwargs)

class ValueProvider(Provider):
    def __init__(self, value):
        self.value = value
        self.params = self.scopes = ()

    def create(self):
        return self.value

def parse_provider(module):
    if isinstance(module, (list, tuple)):
        token, provider = module[0], create_provider(module[1])
    else:
        token = get_token(module)
        provider = create_provider(module)
    return token, provider


def create_provider(token):
    if getattr(token, '_nodefault', False):
        raise Exception("Cannot create default provider for token {!r}".format(token))
    if isinstance(token, Provider):
        return token
    if callable(token):
        return FactoryProvider(token, get_params(token), get_scopes(token))
    raise Exception("Cannot create default provider for token {!r}".format(token))

class Injector(object):
    def __init__(self, modules=(), parent=None, providers=None, scopes=()):
        self._cache = {}
        self._providers = providers if providers is not None else {}
        self._parent = parent
        self._scopes = scopes
        for module in modules:
            token, provider = parse_provider(module)
            self._providers[token] = provider

    def release(self):
        for token, value in self._cache.items():
            provider = self._providers[token]
            if hasattr(provider, 'release'):
                provider.release(value)


    def _hasProviderFor(self, token):
        if token in self._providers:
            return True
        if self._parent:
            return self._parent._hasProviderFor(token)
        return False

    def _instantiateDefaultProvider(self, provider, token, resolving):
        '''Instantiate this provider at the right level and return the result.

        If we have no parent, then this is trivially "the right level" because
        there aren't any others. Otherwise, this is the right level if this
        Injector clears things at a scope that this provider should be cleared
        at. Otherwise, this propagates upwards to the parent.

        So, for example, if you create an Injector i1 with no scope, and then
        give it a child i2 with, say, a scope called RequestScope, then any
        provider that's decorated with RequestScope will be created on i2
        instead of i1. That way, if you later create another i3 with
        RequestScope, it'll have its own instance from that provider instead
        of using the one generated by i2.
        '''
        if not self._parent:
            self._providers[token] = provider
            return self._get(token, resolving)
        for scope in self._scopes:
            if provider.clearedAtScope(scope):
                self._providers[token] = provider
                return self._get(token, resolving)
        return self._parent._instantiateDefaultProvider(provider, token, resolving)

    def get(self, token):
        return self._get(token, set())

    def _get(self, token, resolving):
        # Special case - Injector -> self
        if token is Injector:
            return self
        # If it's in the cache, return it
        if token in self._cache:
            return self._cache[token]
        # If we don't have a provider, and neither do any parents, build a default provider
        if not self._hasProviderFor(token):
            provider = create_provider(token)
            return self._instantiateDefaultProvider(provider, token, resolving)
        provider = self._providers.get(token)
        if not provider:
            # If we get here, then we don't have a provider for this but some parent does.
            return self._parent._get(token, resolving)
        # Actually invoke the provider
        if token in resolving:
            raise Exception("Cyclic or duplicate dependency: {!r}".format(token))
        resolving.add(token)
        args = []
        for param in provider.params:
            args.append(self._get(param.token, resolving))
        instance = provider.create(*args)
        if TransientScope not in provider.scopes:
            self._cache[token] = instance
        return instance

    def _collectProvidersWithScope(self, scopeCls, collectedProviders):
        for token, provider in self._providers.items():
            if token in collectedProviders:
                continue
            if provider.clearedAtScope(scopeCls):
                collectedProviders[token] = provider
        if self._parent:
            self._parent._collectProvidersWithScope(scopeCls, collectedProviders)

    def createChild(self, modules=(), forcedResetScopes=()):
        forcedProviders = {}
        forcedResetScopes = list(forcedResetScopes) + [TransientScope]
        for scope in forcedResetScopes:
            self._collectProvidersWithScope(scope, forcedProviders)
        return Injector(modules, self, forcedProviders, forcedResetScopes)
