import app
from app import Application
import util


def main():
    try:
        app.app = Application()
        app.app.run()
    except Exception:
        # Maybe send an automated e-mail to me on Exception in the future?
        util.logger.exception("Main")
        _ = input("Press enter to quit")


if __name__ == "__main__":
    main()
