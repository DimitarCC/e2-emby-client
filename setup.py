from setuptools import setup
import setup_translate

pkg = "Extensions.E2EmbyClient"
setup(
    name="enigma2-plugin-extensions-e2embyclient",
    version="1.0",
    author="DimitarCC",
    description="An enigma2 client for Emby servers",
    package_dir={pkg: "src"},
    packages=[pkg],
    package_data={pkg: ["*.png", "*.xml", "locale/*/LC_MESSAGES/*.mo"]},
    cmdclass=setup_translate.cmdclass,  # for translation
)
