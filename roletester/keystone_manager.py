import os
import types
import binascii
from Crypto.Cipher import AES
from Crypto import Random
from clients import ClientManager
from string import ascii_letters, digits


class KeystoneManager(object):
    """
    Class for ensuring role assignments in keystone.

    Give it a role assignment, and it will return a user
    that matches your demands. That may include making 
    any missing components (i.e., domain, project, user,
    role) and return back a fresh user. 
    """
    
    def __init__(self):
        """
        This is what holds the decryption keys for the hashes.
        It's really important that this doesn't change during
        a run, or you'll get different outputs.
    
        :param key: The shared key used for 2 way encryption.
        :type key: 16 character length string.
        :param iv: The initialization vector for reversing a hash.
        :type iv: binary number in bytes
        """
        self.__crypto_info = {
            'key': "Sixteen byte key",
            'iv': None #This gets populated on first use.
        }
        
        """
        This is the big map of users. The key is a representation
        of its role assignment (domain, project, role). The value
        is a credentials object.
        """
        self.__users = {}

        """
        These credentials are so that we can create anything we 
        need to in keystone. They must be admin level credentials.
        """
        self.admin_client_manager = self.load_admin_client_manager()
        
    def load_admin_client_manager(self):
        """
        Loads admin credentials from ENV variables
        
        :returns: client.ClientManager
        """
        env_vars_default = {
            'OS_USERNAME': 'admin', 
            'OS_PASSWORD': '', 
            'OS_PROJECT_NAME': 'admin', 
            'OS_AUTH_URL': 'http://127.0.0.1:5000/v3', 
            'OS_USER_DOMAIN_NAME': 'Default', 
            'OS_PROJECT_DOMAIN_NAME': 'Default'}
        env_vars = {
            k[3:].lower(): os.getenv(k, v) 
            for (k,v) in env_vars_default.items()
        }

        return ClientManager(**env_vars)

    def get_random_string(self, length):
        """
        Generates really nice random strings
        :param length: random string length
        :type length: int
        :returns: string
        """
        return ''.join(
            [Random.random.choice(ascii_letters + digits)
            for x in range(length)]

    def _get_cypher(self):
        """
        Builds a cypher for encryption/decryption
        
        :returns: (Crypto.Cipher.AES, bytes)
        """
        key = self.__crypto_info['key']
        iv = None
        if self.__crypto_info['iv'] == None:
            iv = Random.new().read(AES.block_size)
            self.__crypto_info['iv'] = iv
        else:
            iv = self.__crypto_info['iv']
        return (AES.new(key, AES.MODE_CFB, iv), iv)

    def find_user_credentials(self, domain='default', project='default', role='member'):
        """
        Finds a user that matches your auth needs, creating one if necessary.
        
        :param domain: Keystone domain. Defaults to project's value.
        :type domain: string
        :param project: Keystone project. Default to `Default`
        :type project: string
        :param role: Keystone role. If left empty, will default to member
        :type role: string
        :returns: clients.ClientManager
        """
        if domain == '' or domain == None:
            domain = project
        hash = self._encode_hash(domain, project, role)
        if hash in self.__users.keys():
            return self.__users[hash]
        else:
            str_suffix = self.get_random_string(6)
            domain_resource = self._ensure_keystone_resource(
                "domain", 
                "test-domain-%s" % str_suffix)
            project_resource = self._ensure_keystone_resource(
                "project", 
                "test-project-%s" % str_suffix, 
                domain)
            user_resource = self._ensure_keystone_resource(
                "user", 
                "test-user-%s" % str_suffix, 
                domain, 
                project)
            role_resource = self._ensure_keystone_resource(
                "role", 
                "test-role-%s" % str_suffix)
            self.__users[hash] = self.admin_client_manager
            #TODO: Make this return real user name
            return self.__users[hash]
            
    def get_resource_by_name(name, resource_type):
        """
        Returns a keystone resource by name.
        
        Assumes names are unique, or at very least will just 
        return the first matching entity.
        :param name: name of the object to find
        :type name: string
        :param resource_type: name of object type
        :type resource_type: string
        :returns: keystoneclient.base.Resource
        """
        collection = [x 
            for x in ks_attr(resource_type).list() 
            if x.name == name]
        if collection == []:
            return None
        else:
            return collection[0]
            

    def _encode_hash(self, *args):
        """
        Hashes a list of *args into a single value.
        
        :param: list of strigs to pack
        :type *args: [string]
        :returns: string
        """
        text = '|'.join(args)
        (cipher, iv) = self._get_cypher()
        msg = iv + cipher.encrypt(text)
        return msg.encode('hex')


    def _decode_hash(self, hash):
        """
        Decodes a hashed string created by _encode_hash().
        
        Not really used, but handy to have in case something goes sideways.
        
        :param hash: A hashed list
        :type hash: string
        :returns: string
        """
        (cipher, iv) = self._get_cypher()
        return cipher.decrypt(hash.decode('hex'))[len(iv):].split('|')
        
    def _entity_exists(self, keystone_type, name):
        """
        Checks to see if keystone has a matching record.
        
        :param keystone_type: Keystone resource "project" || "domain" || "role"
        :type keystone_type: string
        :param name: matching name, like `member` for a role
        :type name: string
        :returns: boolean
        """
        ks = self.admin_client_manager.get_keystone()
        return name in [x.name for x in getattr(ks, keystone_type).list()]
        
    def _ensure_keystone_resource(self, keystone_resource_type, name, domain_name=None, project_name=None):
        """
        Gets (or creates and returns) a keystone domain by name.
        
        :param name: Keystone domain name
        :type name: string
        :returns: keystoneclient.v3.domains.Domain
        """
        
        ks = self.admin_client_manager.get_keystone() # used like, everywhere
        
        """
        keystone clients are all plural, like `domains` and `users`.
        """
        pluralize = lambda n: "%ss" % n

        """
        quick conversion from a string to the keystone type it represents.
        """
        ks_attr = lambda t: getattr(ks, pluralize(t))
        
        """
        check whether a keystone object exists in its list by name.
        :returns: boolean
        """
        entity_exists = lambda name: name in [x.name for x in resources.list()]

        def build_args(xs, ys, trailing={}, all={}):
            """
            Compiles a struct of args passed into keystone clients
            
            Each keystone type takes the parent types as options
            to create(). Thus user has one more options than project,
            and project one more than domain.
            
            :param xs: keystone entities to be searched.
            :type xs: ['domain', 'project', 'user]
            :param ys: the args from this function. Order is key.
            :type ys: [string]
            :returns: dict
            """
            if xs == []:
                return all
            else:
                all[xs[-1]] = ys
                return build_args(xs[:-1], ys[:-1], trailing, all)
                
        resources = ks_attr(keystone_resource_type) #clarity
        
        xs = ['domain', 'project', 'user']
        ys = [name, 
            self.get_resource_by_name(domain_name, 'domain'), 
            self.get_resource_by_name(project_name, 'project')]
        all_args = build_args(xs, ys)
        

        if entity_exists(name) == False:
            my_args = all_args[keystone_resource_type]
            if keystone_resource_type == 'user':
                # Password field is conveniently last in *args position
                password = ''
                    .join(
                        [Random.random.choice(ascii_letters + digits)
                    for x in range(32)]
                my_args.append(password)
                # Hijack the user, add password so we can slurp it on return
                user = resources.create(*my_args)
                user.password = self.get_random_string(32)
                return user
            else:
                return resources.create(*my_args)
        else:
            return [resources.get(x.id) 
                for x in resources.list() 
                if x.name == name][0]

