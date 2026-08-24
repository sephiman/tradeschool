// SPDX-License-Identifier: AGPL-3.0-only
//
// The JVM half of the shortest-repr contract (Phase W2). Sibling of LibmParityCheck.java, and there
// for the same reason: a claim about what another language prints should be measured on that language,
// not remembered.
//
// A canonical document is JSON, so every double in it becomes text, and the text is what gets hashed.
// CPython's json module writes `repr(float)`, i.e. the SHORTEST string that round-trips. The JVM's
// `Double.toString` also round-trips but chooses differently: it switches to exponential notation
// outside [1e-3, 1e7) and always writes a digit before the point and an exponent without a sign or a
// leading zero. So `0.0001` is `1.0E-4` on the JVM and `0.0001` in Python — and 0.0001 is the display
// quantum of every momentum pane in this course.
//
// Reads the `formatter-cases.tsv` this repo exports (name, hex, python) and prints its own column, so
// a port can diff the three side by side.
//
//   cd backend/scripts/kotlin_side && java DoubleReprCheck.java ../../../dist/contracts/generation-goldens/formatter-cases.tsv
//
// With no argument it prints the built-in case list, which is how the exported `jvm` column was
// measured in the first place.

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DoubleReprCheck {
    private static final long[] BUILT_IN_BITS = {
        Double.doubleToRawLongBits(1e-5),
        Double.doubleToRawLongBits(1e-4),
        Double.doubleToRawLongBits(0.0001),
        Double.doubleToRawLongBits(-0.0001),
        Double.doubleToRawLongBits(0.001),
        Double.doubleToRawLongBits(1e-7),
        Double.doubleToRawLongBits(1e16),
        Double.doubleToRawLongBits(1e21),
        Double.doubleToRawLongBits(1e7),
        Double.doubleToRawLongBits(1234567.0),
        Double.doubleToRawLongBits(12345678.0),
        Double.doubleToRawLongBits(0.1 + 0.2),
        Double.doubleToRawLongBits(-0.0),
        Double.doubleToRawLongBits(1.0),
        Double.doubleToRawLongBits(27000.0),
        Double.doubleToRawLongBits(Double.MIN_VALUE),
        Double.doubleToRawLongBits(Double.MAX_VALUE),
        Double.doubleToRawLongBits(4.9e-324),
        Double.doubleToRawLongBits(2.2250738585072014e-308),
    };

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            System.out.println("hex\tjvm");
            for (long bits : BUILT_IN_BITS) {
                System.out.println(hex(bits) + "\t" + Double.toString(Double.longBitsToDouble(bits)));
            }
            return;
        }
        int rows = 0;
        int differing = 0;
        System.out.println("name\thex\tpython\tjvm\tagree");
        try (BufferedReader reader = Files.newBufferedReader(Path.of(args[0]))) {
            String line;
            boolean header = true;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("#") || line.isBlank()) {
                    continue;
                }
                if (header) {
                    header = false;  // the column header
                    continue;
                }
                String[] cell = line.split("\t", -1);
                long bits = Long.parseUnsignedLong(cell[1].substring(2), 16);
                String jvm = Double.toString(Double.longBitsToDouble(bits));
                boolean agree = jvm.equals(cell[2]);
                if (!agree) {
                    differing++;
                }
                rows++;
                System.out.println(cell[0] + "\t" + cell[1] + "\t" + cell[2] + "\t" + jvm + "\t" + agree);
            }
        }
        System.out.println("# " + rows + " cases, " + differing + " where Double.toString differs from repr()");
    }

    private static String hex(long bits) {
        return "0x" + String.format("%016x", bits);
    }
}
