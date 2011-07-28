import hashlib
import random
import string
import struct
import time


NANOSECOND = int(1e9)


class RandomContentFile(object):
    def __init__(self, size, seed):
        self.size = size
        self.seed = seed
        self.random = random.Random(self.seed)

        # Boto likes to seek once more after it's done reading, so we need to save the last chunks/seek value.
        self.last_chunks = self.chunks = None
        self.last_seek = None

        # Let seek initialize the rest of it, rather than dup code
        self.seek(0)

    def _mark_chunk(self):
        self.chunks.append([self.offset, int(round((time.time() - self.last_seek) * NANOSECOND))])

    def seek(self, offset):
        assert offset == 0
        self.random.seed(self.seed)
        self.offset = offset
        self.buffer = ''

        self.hash = hashlib.md5()
        self.digest_size = self.hash.digest_size
        self.digest = None

        # Save the last seek time as our start time, and the last chunks
        self.last_chunks = self.chunks
        # Before emptying.
        self.last_seek = time.time()
        self.chunks = []

    def tell(self):
        return self.offset

    def _generate(self):
        # generate and return a chunk of pseudorandom data
        # 256 bits = 32 bytes at a time
        size = 1*1024*1024
        l = [self.random.getrandbits(64) for _ in xrange(size/8)]
        s = struct.pack((size/8)*'Q', *l)
        return s

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.offset

        r = []

        random_count = min(size, self.size - self.offset - self.digest_size)
        if random_count > 0:
            while len(self.buffer) < random_count:
                self.buffer += self._generate()
            self.offset += random_count
            size -= random_count
            data, self.buffer = self.buffer[:random_count], self.buffer[random_count:]
            if self.hash is not None:
                self.hash.update(data)
            r.append(data)

        digest_count = min(size, self.size - self.offset)
        if digest_count > 0:
            if self.digest is None:
                self.digest = self.hash.digest()
                self.hash = None
            self.offset += digest_count
            size -= digest_count
            data = self.digest[:digest_count]
            r.append(data)

        self._mark_chunk()

        return ''.join(r)

class FileVerifier(object):
    def __init__(self):
        self.size = 0
        self.hash = hashlib.md5()
        self.buf = ''
        self.created_at = time.time()
        self.chunks = []

    def _mark_chunk(self):
        self.chunks.append([self.size, int(round((time.time() - self.created_at) * NANOSECOND))])

    def write(self, data):
        self.size += len(data)
        self.buf += data
        digsz = -1*self.hash.digest_size
        new_data, self.buf = self.buf[0:digsz], self.buf[digsz:]
        self.hash.update(new_data)
        self._mark_chunk()

    def valid(self):
        """
        Returns True if this file looks valid. The file is valid if the end
        of the file has the md5 digest for the first part of the file.
        """
        if self.size < self.hash.digest_size:
            return self.hash.digest().startswith(self.buf)

        return self.buf == self.hash.digest()

def files(mean, stddev, seed=None):
    """
    Yields file-like objects with effectively random contents, where
    the size of each file follows the normal distribution with `mean`
    and `stddev`.

    Beware, the file-likeness is very shallow. You can use boto's
    `key.set_contents_from_file` to send these to S3, but they are not
    full file objects.

    The last 128 bits are the MD5 digest of the previous bytes, for
    verifying round-trip data integrity. For example, if you
    re-download the object and place the contents into a file called
    ``foo``, the following should print two identical lines:

      python -c 'import sys, hashlib; data=sys.stdin.read(); print hashlib.md5(data[:-16]).hexdigest(); print "".join("%02x" % ord(c) for c in data[-16:])' <foo

    Except for objects shorter than 16 bytes, where the second line
    will be proportionally shorter.
    """
    rand = random.Random(seed)
    while True:
        while True:
            size = int(rand.normalvariate(mean, stddev))
            if size >= 0:
                break
        yield RandomContentFile(size=size, seed=rand.getrandbits(32))

def names(mean, stddev, charset=None, seed=None):
    """
    Yields strings that are somewhat plausible as file names, where
    the lenght of each filename follows the normal distribution with
    `mean` and `stddev`.
    """
    if charset is None:
        charset = string.ascii_lowercase
    rand = random.Random(seed)
    while True:
        while True:
            length = int(rand.normalvariate(mean, stddev))
            if length > 0:
                break
        name = ''.join(rand.choice(charset) for _ in xrange(length))
        yield name
