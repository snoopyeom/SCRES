import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

// BaSyx imports - the BaSyx SDK jars must be on the classpath
import org.eclipse.basyx.aas.metamodel.map.descriptor.*;
import org.eclipse.basyx.aas.metamodel.map.AASXPackageManager;
import org.eclipse.basyx.aas.metamodel.map.AssetAdministrationShellEnvironment;
import org.eclipse.basyx.aas.factory.json.AASJSONDeserializer;

/**
 * Utility to load a normalised AAS JSON file and export it as an AASX package.
 * <p>
 * Usage: java -cp "basyx-sdk.jar:." BaSyxAasCreator input.json output.aasx
 */
public class BaSyxAasCreator {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.out.println("Usage: java BaSyxAasCreator input.json output.aasx");
            return;
        }

        String input = args[0];
        String output = args[1];

        // Read the JSON environment
        try (FileInputStream fis = new FileInputStream(input)) {
            AssetAdministrationShellEnvironment env = new AASJSONDeserializer().read(fis);

            // Export to AASX package
            try (FileOutputStream fos = new FileOutputStream(output)) {
                new AASXPackageManager().writeAASX(fos, env, Files.createTempDirectory("aasx"));
            }
        }
    }
}
