from jugular import Inject, Provide, Injector, Scope, NoDefault


# Things at RequestScope happen per-request, but there may be multiple
# transactions within one request
class RequestScope(Scope): pass

# Things at TransactionScope happen more granularly than at RequestScope.
class TransactionScope(RequestScope): pass

# injection tokens don't have to be callable - they can be anything. But we
# can only infer a default provider if they're callables.

@Inject("config")
class Database(object):
    def __init__(self, config):
        self.config = config
        print("Connecting to {}...".format(config.db_name))
        self.data = dict(
            id1='Adalwin',
            id2='Despina',
            id3='Unathi',
        )

    def get_name(self, uid):
        return self.data.get(uid, None)

    def release(self):
        print("Disconnecting.")

# NoDefault explicitly tells the system not to try to make a default provider
# for Credentials. Alternatively, you could just use a string identifier, or
# maybe an abstract base class?
@NoDefault
class Credentials(object):
    def __init__(self, user_id):
        self.user_id = user_id

class LoginError(Exception): pass

# The RequestScope decorator means that when we have an injector i and we
# create a child with i2 = i.createChild(forcedResetScopes=[RequestScope]), i2
# will NOT inherit i's value for Session, but will instead create its own when
# it's first requested.
@Inject(Database, "config", Credentials)
@RequestScope
class Session(object):
    def __init__(self, db, conf, cred):
        self.conf = conf
        self.db = db
        self.name = self.db.get_name(cred.user_id)
        if not self.name:
            raise LoginError()
        print("Logged in as {} ({})".format(self.name, cred.user_id))

    def release(self):
        if self.name:
            print("Logging out {}!".format(self.name))

@TransactionScope
@Inject(Database)
class DBTransaction(object):
    count = 0
    def __init__(self, db):
        self.db = db
        self.id = DBTransaction.count
        DBTransaction.count += 1

    def release(self):
        print("Committing transaction {}".format(self.id))

@Inject(DBTransaction)
@TransactionScope
class UnitOfWork(object):
    def __init__(self, txn):
        self.txn = txn

    def doit(self):
        print("Doing some work in transaction {}...".format(self.txn.id))

@Inject(Session, Injector)
@RequestScope
class Endpoint(object):
    def __init__(self, session, injector):
        self.session = session
        self.injector = injector

    def serve(self):
        for i in range(3):
            sub = self.injector.createChild([], [TransactionScope])
            sub.get(UnitOfWork).doit()
            sub.release()
        return "Hello, {}!".format(self.session.name)

@Provide("config")
class Config(object):
    db_name = "fake.dat"

# Getting with no injections fails, because we can't build a default provider
# for the string "config"
try:
    Injector().get(Database)
except Exception as e:
    print(e.args[0])
    assert e.args[0] == "Cannot create default provider for token 'config'"
else:
    raise Exception("That should have failed.")

i = Injector([Config])
# The database doesn't need anything but the config, so it works
db = i.get(Database)
print(db.get_name("id3"))

# The session will fail because Credentials has NoDefault set.
try:
    i.get(Session)
except Exception as e:
    assert e.args[0] == "Cannot create default provider for token <class '__main__.Credentials'>"
else:
    raise Exception("That should have failed.")

def handle_request(user_id):
    i2 = i.createChild([(Credentials, lambda:Credentials(user_id))], [RequestScope])
    assert i2.get(Database) is db # i2 uses the root database
    ep = i2.get(Endpoint)
    print(ep.serve())
    i2.release()

handle_request('id1')
handle_request('id2')
i.release()