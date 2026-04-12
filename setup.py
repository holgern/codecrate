from setuptools import setup

setup(
    use_scm_version={
        "write_to": "codecrate/_version.py",
        "fallback_version": "0+unknown",
    },
    setup_requires=["setuptools_scm"],
)
