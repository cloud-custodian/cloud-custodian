# Fuzzing
This folder contains a minor set up for fuzzing Cloud-custodian.

Fuzzing as a concept aims to stress-test the code under analysis. Traditional fuzzing is based on sending random input to the target application, whereas modern fuzzing relies on genetic algorithms based on code-coverage.

Although fuzzing has proven high successful in many cases, e.g. [OSS-Fuzz](https://github.com/google/oss-fuzz) Cloud-custodian is not well-suited for fuzzing and there is likely not a lot to come for. The reasons being:
- Cloud-custodian has a very flat architecture. There is not a ton of complex parsing routines in the library.
- The threat model of cloud custodian means we dont deal with a lot of untrusted input.

Important dependencies e.g. `jsonschema` and `pyyaml` are already being fuzzed by OSS-Fuzz [here](https://github.com/google/oss-fuzz/tree/master/projects/jsonschema) and [here](https://github.com/google/oss-fuzz/tree/master/projects/pyyaml) respectively.


## Cloud-custodian fuzzing
We keep a small set of fuzzers based on the [Atheris](https://github.com/google/atheris) fuzzer.

At the moment we run the fuzzers by hand. To install and run these fuzzers, you can follow the steps after having cloned Cloud-custodian:
```
virtualenv --python=/usr/bin/python3 venv
. venv/bin/activate
pip3 install .
pip3 install atheris
python3 ./tests/fuzzing/FUZZ_NAME
```
where `FUZZ_NAME` is the name of the fuzzer you want to run.

For example, to run the `fuzz_general.py` fuzzer:
```
$ python3 ./tests/fuzzing/fuzz_general.py
...
...
INFO: Running with entropic power schedule (0xFF, 100).
INFO: Seed: 1621127349
INFO: Loaded 1 modules   (37136 inline 8-bit counters): 37136 [0x221e7e0, 0x22278f0), 
INFO: Loaded 1 PC tables (37136 PCs): 37136 [0x7f2962760010,0x7f29627f1110), 
INFO: -max_len is not provided; libFuzzer will not generate inputs larger than 4096 bytes
INFO: A corpus is not provided, starting from an empty corpus
#2      INITED cov: 122 ft: 122 corp: 1/1b exec/s: 0 rss: 60Mb
#6      NEW    cov: 148 ft: 148 corp: 2/3b lim: 4 exec/s: 0 rss: 60Mb L: 2/2 MS: 4 ShuffleBytes-ChangeByte-InsertByte-ChangeBit-
#7      NEW    cov: 178 ft: 188 corp: 3/5b lim: 4 exec/s: 0 rss: 60Mb L: 2/2 MS: 1 InsertByte-
#14     NEW    cov: 178 ft: 190 corp: 4/8b lim: 4 exec/s: 0 rss: 60Mb L: 3/3 MS: 2 ShuffleBytes-CopyPart-
#36     NEW    cov: 178 ft: 192 corp: 5/12b lim: 4 exec/s: 0 rss: 60Mb L: 4/4 MS: 2 ChangeBinInt-CopyPart-
#42     NEW    cov: 179 ft: 193 corp: 6/15b lim: 4 exec/s: 0 rss: 60Mb L: 3/4 MS: 1 ChangeByte-
#49     NEW    cov: 181 ft: 195 corp: 7/18b lim: 4 exec/s: 0 rss: 60Mb L: 3/4 MS: 2 CrossOver-ShuffleBytes-
#53     REDUCE cov: 181 ft: 195 corp: 7/17b lim: 4 exec/s: 0 rss: 60Mb L: 2/4 MS: 4 CrossOver-ChangeBit-CopyPart-EraseBytes-
#110    NEW    cov: 185 ft: 199 corp: 8/21b lim: 4 exec/s: 0 rss: 60Mb L: 4/4 MS: 2 ChangeBit-ChangeBinInt-
#182    REDUCE cov: 185 ft: 199 corp: 8/20b lim: 4 exec/s: 0 rss: 60Mb L: 3/4 MS: 2 ChangeBit-CrossOver-
#218    REDUCE cov: 185 ft: 199 corp: 8/19b lim: 4 exec/s: 0 rss: 60Mb L: 2/4 MS: 1 EraseBytes-
#238    REDUCE cov: 189 ft: 203 corp: 9/21b lim: 4 exec/s: 0 rss: 60Mb L: 2/4 MS: 5 EraseBytes-InsertByte-CrossOver-CrossOver-InsertByte-
#310    NEW    cov: 189 ft: 241 corp: 10/24b lim: 4 exec/s: 0 rss: 60Mb L: 3/4 MS: 2 CrossOver-CopyPart-
#360    REDUCE cov: 190 ft: 242 corp: 11/28b lim: 4 exec/s: 0 rss: 60Mb L: 4/4 MS: 5 CopyPart-InsertByte-InsertByte-ChangeBinInt-CMP- DE: "//"-
#427    NEW    cov: 191 ft: 244 corp: 12/32b lim: 4 exec/s: 0 rss: 60Mb L: 4/4 MS: 2 PersAutoDict-InsertByte- DE: "//"-
#668    NEW    cov: 191 ft: 245 corp: 13/37b lim: 6 exec/s: 0 rss: 60Mb L: 5/5 MS: 1 CopyPart-
```
