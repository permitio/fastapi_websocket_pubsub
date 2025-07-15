from setuptools import setup, find_packages
import os


def get_requirements(env=""):
    if env:
        env = "-{}".format(env)
    req_file = "requirements{}.txt".format(env)
    if os.path.exists(req_file):
        with open(req_file) as fp:
            return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]
    else:
        # Fallback requirements if file not found
        return [
            "fastapi-websocket-rpc>=0.1.25,<1",
            "packaging>=20.4",
            "pydantic>=1.9.1",
            "websockets>=14.0",
            "permit-broadcaster>=0.2.5,<1",
        ]


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fastapi_websocket_pubsub",
    version="1.0.2",
    author="Or Weis",
    author_email="or@permit.io",
    description="A fast and durable PubSub channel over Websockets (using fastapi-websockets-rpc).",
    long_description_content_type="text/markdown",
    long_description=long_description,
    url="https://github.com/permitio/fastapi_websocket_pubsub",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
    ],
    python_requires=">=3.9",
    install_requires=get_requirements(),
    extras_require = {
        "redis": ["permit-broadcaster[redis]>=0.2.5,<1"],
        "postgres": ["permit-broadcaster[postgres]>=0.2.5,<1"],
        "kafka": ["permit-broadcaster[kafka]>=0.2.5,<1"],
        "all": ["permit-broadcaster[redis,postgres,kafka]>=0.2.5,<1"],
    }
)
