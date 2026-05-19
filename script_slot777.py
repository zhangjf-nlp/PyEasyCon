from gui import run_script
from scripts.hit import sleep

delay = 0.860

VERSION = "fr"  # "fr" 火红 / "lg" 叶绿
COLUMN_LABELS = {
    "fr": ["火红老虎机第一列", "火红老虎机第二列", "火红老虎机第三列"],
    "lg": ["叶绿老虎机第一列", "叶绿老虎机第二列", "叶绿老虎机第三列"],
}


def main(ctx):
    labels = COLUMN_LABELS[VERSION]

    while ctx.is_running():
        while ctx.is_running():
            for _ in range(3):
                ctx.press("DOWN")
            if not ctx.search_label("3代老虎机上3", 90):
                if not ctx.search_label("3代老虎机下3", 90):
                    break

        sleep(0.5)
        missed = False

        for label in labels:
            while ctx.is_running():
                if missed:
                    ctx.press("A")
                    break
                elif ctx.search_label(label, 95):
                    sleep(delay)
                    ctx.press("A")
                    sleep(0.5)
                    missed = not ctx.search_label(label, 95)
                    break
                else:
                    sleep(0.5)

        sleep(0.5)

        ctx.hold("A")
        while ctx.is_running():
            if ctx.search_label("3代老虎机入账", 95):
                if ctx.search_label("3代老虎机上3", 90):
                    if ctx.search_label("3代老虎机下3", 90):
                        break
            sleep(0.2)
        ctx.release("A")
        
        for _ in range(3):
            if ctx.search_label('9999代币', 100):
                sleep(0.5)
            else:
                break
        else:
            ctx.log("代币已满9999，停止运行")
            break


if __name__ == "__main__":
    run_script(main)