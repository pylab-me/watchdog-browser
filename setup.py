from setuptools import setup


setup(
    name="watchdog-browser",
    version="0.1.1",
    description="Playwright-based browser auth state refresh worker",
    packages=["watchdog_browser"],
    package_dir={"watchdog_browser": "src"},
    include_package_data=True,
    python_requires=">=3.12",
    install_requires=[
        "playwright>=1.58.0",
        "SQLAlchemy>=2.0.48",
        "psycopg2-binary>=2.9.11",
    ],
    entry_points={
        "console_scripts": [
            "watchdog-browser-worker=watchdog_browser.main:main",
            "watchdog-browser-bootstrap=watchdog_browser.bootstrap_task:main",
        ]
    },
)
