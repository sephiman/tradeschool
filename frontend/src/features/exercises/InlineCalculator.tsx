import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

function cleanResult(val: number): string {
  if (!Number.isFinite(val)) return "Error";
  // Trim floating point artifacts up to 10 decimals
  const str = Number(val.toFixed(10)).toString();
  return str;
}

export function InlineCalculator({
  onUseResult,
}: {
  onUseResult?: (val: string) => void;
}) {
  const { t } = useTranslation();
  const [display, setDisplay] = useState("0");
  const [expression, setExpression] = useState("");
  const [prevValue, setPrevValue] = useState<number | null>(null);
  const [op, setOp] = useState<"+" | "-" | "*" | "/" | null>(null);
  const [waitingForOperand, setWaitingForOperand] = useState(false);
  const [memory, setMemory] = useState<number | null>(null);

  const inputDigit = (digit: string) => {
    if (waitingForOperand) {
      setDisplay(digit);
      setWaitingForOperand(false);
    } else {
      setDisplay(display === "0" ? digit : display + digit);
    }
  };

  const inputDot = () => {
    if (waitingForOperand) {
      setDisplay("0.");
      setWaitingForOperand(false);
      return;
    }
    if (!display.includes(".")) {
      setDisplay(display + ".");
    }
  };

  const clearAll = () => {
    setDisplay("0");
    setExpression("");
    setPrevValue(null);
    setOp(null);
    setWaitingForOperand(false);
  };

  const backspace = () => {
    if (waitingForOperand) return;
    if (display.length <= 1 || (display.length === 2 && display.startsWith("-"))) {
      setDisplay("0");
    } else {
      setDisplay(display.slice(0, -1));
    }
  };

  const toggleSign = () => {
    const current = parseFloat(display);
    if (isNaN(current) || current === 0) return;
    setDisplay((-current).toString());
  };

  const performOp = (nextOp: "+" | "-" | "*" | "/") => {
    const inputValue = parseFloat(display);

    if (prevValue === null) {
      setPrevValue(inputValue);
      setExpression(`${display} ${nextOp}`);
    } else if (op) {
      const currentVal = prevValue;
      let computed = currentVal;

      if (op === "+") computed = currentVal + inputValue;
      else if (op === "-") computed = currentVal - inputValue;
      else if (op === "*") computed = currentVal * inputValue;
      else if (op === "/") computed = inputValue !== 0 ? currentVal / inputValue : NaN;

      const resStr = cleanResult(computed);
      setPrevValue(computed);
      setDisplay(resStr);
      setExpression(`${resStr} ${nextOp}`);
    }

    setWaitingForOperand(true);
    setOp(nextOp);
  };

  const calculateEqual = () => {
    if (op === null || prevValue === null) return;
    const inputValue = parseFloat(display);
    let computed = prevValue;

    if (op === "+") computed = prevValue + inputValue;
    else if (op === "-") computed = prevValue - inputValue;
    else if (op === "*") computed = prevValue * inputValue;
    else if (op === "/") computed = inputValue !== 0 ? prevValue / inputValue : NaN;

    const resStr = cleanResult(computed);
    setDisplay(resStr);
    setExpression("");
    setPrevValue(null);
    setOp(null);
    setWaitingForOperand(true);
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }

      const key = e.key;

      if (/^[0-9]$/.test(key)) {
        e.preventDefault();
        inputDigit(key);
      } else if (key === "." || key === ",") {
        e.preventDefault();
        inputDot();
      } else if (key === "+") {
        e.preventDefault();
        performOp("+");
      } else if (key === "-") {
        e.preventDefault();
        performOp("-");
      } else if (key === "*" || key.toLowerCase() === "x") {
        e.preventDefault();
        performOp("*");
      } else if (key === "/") {
        e.preventDefault();
        performOp("/");
      } else if (key === "Enter" || key === "=") {
        e.preventDefault();
        calculateEqual();
      } else if (key === "Backspace") {
        e.preventDefault();
        backspace();
      } else if (key === "Escape" || key.toLowerCase() === "c") {
        e.preventDefault();
        clearAll();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [display, prevValue, op, waitingForOperand]);

  // Memory functions
  const memoryClear = () => setMemory(null);
  const memoryRecall = () => {
    if (memory !== null) {
      setDisplay(memory.toString());
      setWaitingForOperand(true);
    }
  };
  const memoryAdd = () => {
    const val = parseFloat(display);
    if (!isNaN(val)) {
      setMemory((memory ?? 0) + val);
    }
  };

  return (
    <div className="w-full max-w-xs rounded-xl border border-border bg-gray-50/90 p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900/90">
      {/* Display header */}
      <div className="mb-2 rounded-lg border border-gray-200 bg-white p-2.5 text-right shadow-inner dark:border-gray-700 dark:bg-gray-950">
        <div className="h-4 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-xs text-gray-400 dark:text-gray-500">
          {expression}
        </div>
        <div className="mt-0.5 overflow-x-auto font-mono text-xl font-bold tracking-wide tabular-nums text-gray-900 dark:text-gray-100">
          {display}
        </div>
      </div>

      {/* Memory & Action row */}
      <div className="mb-2 flex items-center justify-between gap-1">
        <div className="flex gap-1 text-xs">
          <button
            type="button"
            onClick={memoryClear}
            className="rounded border border-border px-1.5 py-0.5 font-mono text-xs text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
            title="Memory Clear"
          >
            MC
          </button>
          <button
            type="button"
            onClick={memoryRecall}
            disabled={memory === null}
            className="rounded border border-border px-1.5 py-0.5 font-mono text-xs text-gray-500 hover:bg-gray-100 disabled:opacity-40 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
            title="Memory Recall"
          >
            MR {memory !== null && "•"}
          </button>
          <button
            type="button"
            onClick={memoryAdd}
            className="rounded border border-border px-1.5 py-0.5 font-mono text-xs text-gray-500 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
            title="Memory Add"
          >
            M+
          </button>
        </div>

        {onUseResult && (
          <Button
            variant="ghost"
            onClick={() => onUseResult(display)}
            className="h-6 px-2 text-xs font-medium text-primary hover:bg-indigo-50 dark:hover:bg-indigo-950/50"
          >
            {t("exercise.useResult")} ↵
          </Button>
        )}
      </div>

      {/* Buttons Grid */}
      <div className="grid grid-cols-4 gap-1.5">
        <button
          type="button"
          onClick={clearAll}
          className="flex h-10 items-center justify-center rounded-md border border-red-200 bg-red-50 text-sm font-semibold text-red-700 hover:bg-red-100 active:scale-95 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300 dark:hover:bg-red-900/60"
        >
          C
        </button>
        <button
          type="button"
          onClick={backspace}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-sm font-medium text-gray-700 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
        >
          ⌫
        </button>
        <button
          type="button"
          onClick={toggleSign}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-sm font-medium text-gray-700 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
        >
          ±
        </button>
        <button
          type="button"
          onClick={() => performOp("/")}
          className={cn(
            "flex h-10 items-center justify-center rounded-md border text-sm font-bold active:scale-95",
            op === "/"
              ? "border-primary bg-primary text-primary-foreground"
              : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:bg-indigo-900/80",
          )}
        >
          ÷
        </button>

        <button
          type="button"
          onClick={() => inputDigit("7")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          7
        </button>
        <button
          type="button"
          onClick={() => inputDigit("8")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          8
        </button>
        <button
          type="button"
          onClick={() => inputDigit("9")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          9
        </button>
        <button
          type="button"
          onClick={() => performOp("*")}
          className={cn(
            "flex h-10 items-center justify-center rounded-md border text-sm font-bold active:scale-95",
            op === "*"
              ? "border-primary bg-primary text-primary-foreground"
              : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:bg-indigo-900/80",
          )}
        >
          ×
        </button>

        <button
          type="button"
          onClick={() => inputDigit("4")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          4
        </button>
        <button
          type="button"
          onClick={() => inputDigit("5")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          5
        </button>
        <button
          type="button"
          onClick={() => inputDigit("6")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          6
        </button>
        <button
          type="button"
          onClick={() => performOp("-")}
          className={cn(
            "flex h-10 items-center justify-center rounded-md border text-sm font-bold active:scale-95",
            op === "-"
              ? "border-primary bg-primary text-primary-foreground"
              : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:bg-indigo-900/80",
          )}
        >
          −
        </button>

        <button
          type="button"
          onClick={() => inputDigit("1")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          1
        </button>
        <button
          type="button"
          onClick={() => inputDigit("2")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          2
        </button>
        <button
          type="button"
          onClick={() => inputDigit("3")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          3
        </button>
        <button
          type="button"
          onClick={() => performOp("+")}
          className={cn(
            "flex h-10 items-center justify-center rounded-md border text-sm font-bold active:scale-95",
            op === "+"
              ? "border-primary bg-primary text-primary-foreground"
              : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:bg-indigo-900/80",
          )}
        >
          +
        </button>

        <button
          type="button"
          onClick={() => inputDigit("0")}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-medium text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          0
        </button>
        <button
          type="button"
          onClick={inputDot}
          className="flex h-10 items-center justify-center rounded-md border border-border bg-white text-base font-bold text-gray-900 hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700"
        >
          .
        </button>
        <button
          type="button"
          onClick={calculateEqual}
          className="col-span-2 flex h-10 items-center justify-center rounded-md border border-primary bg-primary text-base font-bold text-primary-foreground shadow-sm hover:bg-primary/90 active:scale-95"
        >
          =
        </button>
      </div>
    </div>
  );
}
